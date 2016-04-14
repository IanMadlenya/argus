# -*- coding: utf-8 -*-
"""
Training Relevance model happens here, you can change various parameters in train().
"""
import csv
import importlib
import pickle
import sys
import argparse
import scipy.stats as ss
import numpy as np
from keras.optimizers import SGD

import pysts.embedding as emb
from argus.keras_preprocess import config, load_sets, load_and_train, tokenize, Q

outfile = 'tests/feature_prints/all_features.tsv'
trainIDs = []
params = ['dropout=0', 'inp_e_dropout=0', 'pact="tanh"', 'l2reg=0.01']  # can be replaced by script params


def train_and_eval(test_path, rnn_args, save_to_argus=True):
    qs_train, qs_val, qs_test, c_text, r_text = load_features()
    # pickle.dump((qs_train, qs_test, ctext, rtext), open('qs.pkl', 'wb'))
    # qs_train, qs_test, ctext, rtext = pickle.load(open('qs.pkl'))

    zero_features(qs_train, c_text, r_text)
    zero_features(qs_val)
    zero_features(qs_test)

    w_dim = qs_train[0].c.shape[-1]
    q_dim = qs_train[0].r.shape[-1]
    print 'w_dim=', w_dim
    print 'q_dim=', q_dim

    # ==========================================================
    optimizer = 'adam'  # SGD(lr=0.1, decay=1e-6, momentum=0.9, nesterov=True)
    max_sentences = 50

    # ==========================================================
    modelname = 'rnn'
    module = importlib.import_module('.'+modelname, 'models')
    conf, ps, h = config(module.config, params+rnn_args)

    runid = '%s-%x' % (modelname, h)
    print('RunID: %s  (%s)' % (runid, ps))

    print('GloVe')
    glove = emb.GloVe(N=conf['embdim'])

    print('Dataset')
    vocab = pickle.load(open('sources/vocab.txt'))
    y, _, gr = load_sets(qs_train, max_sentences, vocab)
    y, _, grv = load_sets(qs_val, max_sentences, vocab)
    yt, _, grt = load_sets(qs_test, max_sentences, vocab)
    # pickle.dump(vocab, open('sources/vocab.txt', 'wb'))

    model = load_and_train(runid, module.prep_model, conf, glove, vocab, gr, grv, grt,
                           max_sentences, w_dim, q_dim, optimizer, test_path=test_path)

    ###################################

    print('Predict&Eval (best epoch)')
    loss, acc_t = model.evaluate(grt, show_accuracy=True)
    print('Test: loss=', loss, 'acc=', acc_t)
    loss, acc_tr = model.evaluate(gr, show_accuracy=True)
    print('Train: loss=', loss, 'acc=', acc_tr)
    loss, acc_v = model.evaluate(grv, show_accuracy=True)
    print('Val: loss=', loss, 'acc=', acc_v)
    results = (acc_tr, acc_v, acc_t)

    print '\n========================\n'
    # list_weights(R, ctext, rtext)
    # print 'W_shape =', R.W.shape
    # print 'Q_shape =', R.Q.shape
    # print '---------------test'

    # stats(model, x_train, y_train)
    # stats(model, x_test, y_test)

    # print '---------------train'
    # stats(R, qstrain)
    if save_to_argus:
        if query_yes_no('Save model?'):
            model.save_weights('sources/models/full_model.h5', overwrite=True)
        if query_yes_no('Rewrite output.tsv?'):
            print('Predicting for outfile.tsv')
            res_dict = zip(gr['q_texts'], model.predict(gr)['score'][:,0]) + zip(grt['q_texts'], model.predict(grt)['score'][:,0])
            print('Prediction ready')
            rewrite_output(res_dict)

    return results


def load_features():
    clas_ixs, rel_ixs = [], []
    c_text, r_text = [], []
    S, R, C, QS, GS, Q_text = [], [], [], [], [], []
    GS_ix = 0
    i = 0
    for line in csv.reader(open(outfile), delimiter='\t', skipinitialspace=True):
        try:
            line = [s.decode('utf8') for s in line]
        except AttributeError:  # python3 has no .decode()
            pass
        if i == 0:
            i += 1
            for field in line:
                if field == 'Class_GS':
                    GS_ix = line.index(field)
                if '#' in field:
                    clas_ixs.append(line.index(field))
                    c_text.append(field)
                if '@' in field:
                    rel_ixs.append(line.index(field))
                    r_text.append(field)
        if line[0] == 'Question':
            continue
        S.append(tokenize(line[1].lower()))  # FIXME: glove should not use lower()
        Q_text.append(line[0])
        QS.append(tokenize(line[0].lower()))
        R.append([float(line[ix]) for ix in rel_ixs])
        C.append([float(line[ix]) for ix in clas_ixs])
        GS.append(float(line[GS_ix] == 'YES'))
    qs_train = []
    qs_test = []

    q_t = ''
    ixs = []
    for q_text, i in zip(Q_text, range(len(QS))):
        if q_t != q_text:
            ixs.append(i)
            q_t = q_text

    qs_val = []
    for i, i_, j in zip(ixs, ixs[1:]+[len(QS)], range(len(ixs))):
        if split(j) == 'train':
            trainIDs.append(Q_text[i])
            qs_train.append(Q(Q_text[i], QS[i:i_], S[i:i_], np.array(C[i:i_]), np.array(R[i:i_]), GS[i]))
        elif split(j) == 'val':
            trainIDs.append(Q_text[i])
            qs_val.append(Q(Q_text[i], QS[i:i_], S[i:i_], np.array(C[i:i_]), np.array(R[i:i_]), GS[i]))
        else:
            qs_test.append(Q(Q_text[i], QS[i:i_], S[i:i_], np.array(C[i:i_]), np.array(R[i:i_]), GS[i]))

    np.save('tests/trainIDs/trainIDs.npy', np.array(trainIDs))
    return qs_train, qs_val, qs_test, c_text, r_text


from fractions import gcd
split_ = [400, 150, 200]  # absolute or fraction of [train, val, test] split
gcd_ = gcd(split_[0],gcd(split_[1],split_[2]))
split_ = [x/gcd_ for x in split_]
s = sum(split_)
train_split = range(split_[0])
val_split = [split_[0]+x for x in range(split_[1])]
def split(i):
    if i % s in train_split:
        return 'train'
    elif i % s in val_split:
        return 'val'
    else:
        return 'test'


def zero_features(qs, ctext=None, rtext=None):
    """ extend FV with <feature>==0 metafeatures """
    k = 0
    for q in qs:
        flen = q.c.shape[-1]
        for i in range(flen):
            newf = q.c[:, i] == 0
            q.c = np.column_stack((q.c, newf.astype(float)))
            if k == 0 and ctext is not None:
                ctext.append(ctext[i] + '==0')
        k = 1


def list_weights(R, ctext, rtext):
    for i in range(len(ctext)):
        dots = max(3, 50 - len(ctext[i]))
        print '(class) %s%s%.2f' % (ctext[i], '.' * dots, R.W[i])
    print '(class) bias........%.2f' % (R.W[-1])
    for i in range(len(rtext)):
        dots = max(3, 50 - len(rtext[i]))
        print '(rel) %s%s%.2f' % (rtext[i], '.' * dots, R.Q[i])
    print '(rel) bias........%.2f' % (R.Q[-1])


def stats(model, x, y):
    i = len(y)
    y = np.reshape(y, (i, 1))
    y_ = model.predict({'clr_in': x})['clr_out']
    corr = np.sum(np.abs(y-y_) < 0.5).astype('int')
    print '%.2f%% correct (%d/%d)' % (float(corr) / i * 100, corr, i)
    return float(corr) / i * 100


def rewrite_output(results):
    lines = []
    out_tsv = 'tests/outfile.tsv'
    for line in csv.reader(open(out_tsv), delimiter='\t', skipinitialspace=True):
        for qtext, y in results:
            if line[1] == qtext:
                if y > .5:
                    line[3] = 'YES'
                else:
                    line[3] = 'NO'
                line[11] = str(y)
        lines.append(line)
    writer = csv.writer(open(out_tsv, 'wr'), delimiter='\t')
    for line in lines:
        writer.writerow(line)


def query_yes_no(question, default="yes"):
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    prompt = " [y/n] "
    while True:
        sys.stdout.write(question + prompt)
        choice = raw_input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")


def student_distribution_print(fname, r, alpha=0.95, bonferroni=1.):
    if len(r) > 0:
        bar = ss.t.isf((1 - alpha) / bonferroni / 2, len(r) - 1) * np.std(r) / np.sqrt(len(r))
    else:
        bar = np.nan
    print('%s: %f ±%f (%s)' % (fname, np.mean(r), bar, r))
    return bar


def train_full(runs, pars):
    if runs is None:
        runs = 16
    else:
        runs = int(runs)
    results = []
    for i in range(runs):
        print 'Full training, run #%i out of %i' % (i+1, runs)
        np.random.seed(1337+i)
        results.append(train_and_eval(None, pars, False))

    tr_acc = [tr for tr, v, t in results]
    t_acc = [t for tr, v, t in results]
    v_acc = [v for tr, v, t in results]
    print '===========RESULTS==========='
    student_distribution_print('Train', tr_acc)
    student_distribution_print('Val', v_acc)
    student_distribution_print('Test', t_acc)


if __name__ == '__main__':
    np.random.seed(17151711)
    parser = argparse.ArgumentParser()
    parser.add_argument('--test')
    parser.add_argument('--full_runs')
    parser.add_argument('-full', action='store_true')
    args, rnn_args = parser.parse_known_args()
    if vars(args)['full']:
        train_full(vars(args)['full_runs'], rnn_args)
    else:
        train_and_eval(vars(args)['test'], rnn_args)
