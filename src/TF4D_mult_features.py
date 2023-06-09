from keras.layers import BatchNormalization, GlobalAveragePooling1D, Embedding, Flatten, Layer, Dense, Dropout, MultiHeadAttention, Attention, Conv1D, Input, Lambda, Concatenate, LayerNormalization
from sklearn.model_selection import train_test_split
from tensorflow.python.client import device_lib
from keras import Model
from keras.models import Sequential
from keras import backend as K
import tensorflow as tf
import numpy as np
import matplotlib.pyplot as plt
import os

import absl.logging #prevent checkpoint warnings while training
absl.logging.set_verbosity(absl.logging.ERROR)
tf.get_logger().setLevel('ERROR')
tf.autograph.set_verbosity(3)

import os 
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'


def get_angles(pos, i, d_model):
    angle_rates = 1 / np.power(10000, (2 * (i//2)) / np.float32(d_model))
    return pos * angle_rates


def positional_encoding(position, d_model):
    angle_rads = get_angles(np.arange(position)[:, np.newaxis], np.arange(d_model)[
                            np.newaxis, :], d_model)

    # apply sin to even indices in the array; 2i
    angle_rads[:, 0::2] = np.sin(angle_rads[:, 0::2])

    # apply cos to odd indices in the array; 2i+1
    angle_rads[:, 1::2] = np.cos(angle_rads[:, 1::2])
    pos_encoding = angle_rads[np.newaxis, ...]
    return tf.cast(pos_encoding, dtype=tf.float32)


class EncoderLayer(tf.keras.layers.Layer):
    def __init__(self,  d_model=512, num_heads=8, dff=2048, dropout=0.0, norm_layer=True, **kwargs):
        super(EncoderLayer, self).__init__(**kwargs)

        self.norm_layer = norm_layer
        self.multi_head_attention = MultiHeadAttention(d_model, num_heads)

        self.dropout_attention = tf.keras.layers.Dropout(dropout)
        self.add_attention = tf.keras.layers.Add()
        self.layer_norm_attention = tf.keras.layers.LayerNormalization(
            epsilon=1e-6)

        self.dense1 = tf.keras.layers.Dense(dff, activation='relu')
        self.dense2 = tf.keras.layers.Dense(d_model)
        self.dropout_dense = tf.keras.layers.Dropout(dropout)
        self.add_dense = tf.keras.layers.Add()
        self.layer_norm_dense = tf.keras.layers.LayerNormalization(
            epsilon=1e-6)

    def get_config(self):
        config = super(EncoderLayer, self).get_config()
        config.update({
            'multi_head_attention': self.multi_head_attention,
            'dropout_attention': self.dropout_attention,
            'add_attention': self.add_attention,
            'layer_norm_attention': self.layer_norm_attention,
            'dense1': self.dense1,
            'dense2': self.dense2,
            'dropout_dense': self.dropout_dense,
            'add_dense': self.add_dense,
            'layer_norm_dense': self.layer_norm_dense,
            'norm_layer':self.norm_layer
        })
        return config
    
    def build(self, input_shape):
        super(EncoderLayer, self).build(input_shape)

    def call(self, inputs, mask=None, training=None):
        # print(mask)
        attention = self.multi_head_attention(
            [inputs, inputs, inputs], mask=[mask, mask])
        attention = self.dropout_attention(attention, training=training)
        x = self.add_attention([inputs, attention])

        if self.norm_layer:
            x = self.layer_norm_attention(x)
        # x = inputs

        # Feed Forward
        dense = self.dense1(x)
        dense = self.dense2(dense)
        dense = self.dropout_dense(dense, training=training)
        x = self.add_dense([x, dense])

        if self.norm_layer:
            x = self.layer_norm_dense(x)

        return x


class DecoderLayer(tf.keras.layers.Layer):
    def __init__(self,  d_model=512, num_heads=8, dff=2048, dropout=0.0, norm_layer=True, **kwargs):
        super(DecoderLayer, self).__init__(**kwargs)

        self.norm_layer = norm_layer
        self.multi_head_attention1 = MultiHeadAttention(
            d_model, num_heads, causal=True)
        self.dropout_attention1 = tf.keras.layers.Dropout(dropout)
        self.add_attention1 = tf.keras.layers.Add()
        self.layer_norm_attention1 = tf.keras.layers.LayerNormalization(
            epsilon=1e-6)

        self.multi_head_attention2 = MultiHeadAttention(d_model, num_heads)
        self.dropout_attention2 = tf.keras.layers.Dropout(dropout)
        self.add_attention2 = tf.keras.layers.Add()
        self.layer_norm_attention2 = tf.keras.layers.LayerNormalization(
            epsilon=1e-6)

        self.dense1 = tf.keras.layers.Dense(dff, activation='relu')
        self.dense2 = tf.keras.layers.Dense(d_model)
        self.dropout_dense = tf.keras.layers.Dropout(dropout)
        self.add_dense = tf.keras.layers.Add()
        self.layer_norm_dense = tf.keras.layers.LayerNormalization(
            epsilon=1e-6)

    def get_config(self):
        config = super(DecoderLayer, self).get_config()
        config.update({
            'multi_head_attention1': self.multi_head_attention1,
            'dropout_attention1': self.dropout_attention1,
            'add_attention1': self.add_attention1,
            'layer_norm_attention1': self.layer_norm_attention1,
            'multi_head_attention2': self.multi_head_attention2,
            'dropout_attention2': self.dropout_attention2,
            'add_attention2': self.add_attention2,
            'layer_norm_attention2': self.layer_norm_attention2,
            'dense1': self.dense1,
            'dense2': self.dense2,
            'dropout_dense': self.dropout_dense,
            'add_dense': self.add_dense,
            'layer_norm_dense': self.layer_norm_dense,
            'norm_layer':self.norm_layer
        })
        return config

    def build(self, input_shape):
        super(DecoderLayer, self).build(input_shape)

    def call(self, inputs, mask=None, training=None):
        # print(mask)

        attention = self.multi_head_attention1(
            [inputs[0], inputs[0], inputs[0]], mask=[mask[0], mask[0]])
        attention = self.dropout_attention1(attention, training=training)
        x = self.add_attention1([inputs[0], attention])
        
        if self.norm_layer:        
            x = self.layer_norm_attention1(x)

        attention = self.multi_head_attention2(
            [x, inputs[1], inputs[1]], mask=[mask[0], mask[1]])
        attention = self.dropout_attention2(attention, training=training)
        x = self.add_attention1([x, attention])

        if self.norm_layer:    
            x = self.layer_norm_attention1(x)

        # Feed Forward
        dense = self.dense1(x)
        dense = self.dense2(dense)
        dense = self.dropout_dense(dense, training=training)
        x = self.add_dense([x, dense])

        if self.norm_layer:
            x = self.layer_norm_dense(x)

        return x


class MultiHeadAttention(tf.keras.layers.Layer):
    def __init__(self, d_model=512, num_heads=8, causal=False, dropout=0.0, **kwargs):
        super(MultiHeadAttention, self).__init__(**kwargs)

        assert d_model % num_heads == 0

        depth = d_model // num_heads

        self.w_query = tf.keras.layers.Dense(d_model)
        self.split_reshape_query = tf.keras.layers.Reshape(
            (-1, num_heads, depth))
        self.split_permute_query = tf.keras.layers.Permute((2, 1, 3))

        self.w_value = tf.keras.layers.Dense(d_model)
        self.split_reshape_value = tf.keras.layers.Reshape(
            (-1, num_heads, depth))
        self.split_permute_value = tf.keras.layers.Permute((2, 1, 3))

        self.w_key = tf.keras.layers.Dense(d_model)
        self.split_reshape_key = tf.keras.layers.Reshape(
            (-1, num_heads, depth))
        self.split_permute_key = tf.keras.layers.Permute((2, 1, 3))

        self.attention = tf.keras.layers.Attention(
            causal=causal, dropout=dropout)
        self.join_permute_attention = tf.keras.layers.Permute((2, 1, 3))
        self.join_reshape_attention = tf.keras.layers.Reshape((-1, d_model))

        self.dense = tf.keras.layers.Dense(d_model)
        # self.distribution = None
    def build(self, input_shape):
        super(MultiHeadAttention, self).build(input_shape)
    
    def get_config(self):
        config = super(MultiHeadAttention, self).get_config()
        config.update({
            'w_query': self.w_query,
            'split_reshape_query': self.split_reshape_query,
            'split_permute_query': self.split_permute_query,
            'w_value': self.w_value,
            'split_reshape_value': self.split_reshape_value,
            'split_permute_value': self.split_permute_value,
            'w_key': self.w_key,
            'split_reshape_key': self.split_reshape_key,
            'split_permute_key': self.split_permute_key,
            'attention': self.attention,
            'join_permute_attention': self.join_permute_attention,
            'join_reshape_attention': self.join_reshape_attention,
            'dense': self.dense
            # 'distribution':self.distribution
        })
        return config

    def call(self, inputs, mask=None, training=None):
        q = inputs[0]
        v = inputs[1]
        k = inputs[2] if len(inputs) > 2 else v

        query = self.w_query(q)
        query = self.split_reshape_query(query)
        query = self.split_permute_query(query)

        value = self.w_value(v)
        value = self.split_reshape_value(value)
        value = self.split_permute_value(value)

        key = self.w_key(k)
        key = self.split_reshape_key(key)
        key = self.split_permute_key(key)

        if mask is not None:
            if mask[0] is not None:
                mask[0] = tf.keras.layers.Reshape((-1, 1))(mask[0])
                mask[0] = tf.keras.layers.Permute((2, 1))(mask[0])
            if mask[1] is not None:
                mask[1] = tf.keras.layers.Reshape((-1, 1))(mask[1])
                mask[1] = tf.keras.layers.Permute((2, 1))(mask[1])

        attention = self.attention([query, value, key], mask=mask)

        # scores =tf.matmul(query, key, transpose_b=True)
        # distribution = tf.nn.softmax(scores)
        # self.distribution = distribution
            # print("yes")
        attention = self.join_permute_attention(attention)
        attention = self.join_reshape_attention(attention)

        x = self.dense(attention)

        return x

    # def model(self):
    #     x = tf.keras.layers.Input(shape=(None, 4))
    #     return tf.keras.Model(inputs=[x], outputs=self.distribution)

class Encoder(tf.keras.layers.Layer):
    def __init__(self, input_vocab_size=4, num_layers=4, d_model=512, num_heads=8, dff=2048, maximum_position_encoding=100, dropout=0.0, norm_layer=True, **kwargs):
        super(Encoder, self).__init__(**kwargs)

        self.d_model = d_model
        self.norm_layer=norm_layer
        # self.embedding = tf.keras.layers.Embedding(input_vocab_size, d_model, mask_zero=True)
        self.embedding_ = tf.keras.layers.Dense(
            d_model, activation=None, use_bias=False, input_shape=(None,input_vocab_size))  # only weights multiplication
        # self.pos = positional_encoding(maximum_position_encoding, d_model)
        self.pos_emb = tf.keras.layers.Embedding(
            input_dim=maximum_position_encoding, output_dim=d_model)

        self.encoder_layers = [EncoderLayer(
            d_model=d_model, num_heads=num_heads, dff=dff, dropout=dropout, norm_layer=norm_layer) for _ in range(num_layers)]
        # self.att_weights = [None] * len(self.encoder_layers)

        self.dropout = tf.keras.layers.Dropout(dropout)

    def build(self, input_shape):
        super(Encoder, self).build(input_shape)
    
    def get_config(self):
        config = super(Encoder, self).get_config()
        config.update({
            'd_model': self.d_model,
            'embedding_': self.embedding_,
            'pos_emb': self.pos_emb,
            'encoder_layers': self.encoder_layers,
            'dropout': self.dropout,
            'norm_layer':self.norm_layer
            # 'att_weights':self.att_weights
        })
        return config

    def call(self, inputs, mask=None, training=None):
        x = self.embedding_(inputs)

        # positional encoding
        x *= tf.math.sqrt(tf.cast(self.d_model, tf.float32))

        maxlen = tf.shape(x)[1]
        positions = tf.range(start=0, limit=maxlen, delta=1)
        x += self.pos_emb(positions)

        # x += self.pos[: , :tf.shape(x)[1], :]

        x = self.dropout(x, training=training)  

        # Encoder layer
        # embedding_mask = self.embedding_.compute_mask(inputs)
        # self.att_weights = [None] * len(self.encoder_layers)
        for i, encoder_layer in enumerate(self.encoder_layers):
            x = encoder_layer(x)  # , mask = embedding_mask)
            # self.att_weights[i] = encoder_layer.multi_head_attention.attention.weights
            # self.att_weights[i] = encoder_layer.multi_head_attention.distribution


        return x
    # def model(self):
    #     x = tf.keras.layers.Input(shape=(None, 4))
    #     return tf.keras.Model(inputs=[x], outputs=self.call(x))

    # def compute_mask(self, inputs, mask=None):
    #   return self.embedding_.compute_mask(inputs)


class Decoder(tf.keras.layers.Layer):
    def __init__(self, target_vocab_size=4, num_layers=4,num_emb_vec=4, d_model=512, num_heads=8, dff=2048, maximum_position_encoding=100, dropout=0.0, norm_layer=True, **kwargs):
        super(Decoder, self).__init__(**kwargs)

        self.norm_layer=norm_layer
        self.d_model = d_model
        self.feature_embeddings = [Sequential(
            [tf.keras.layers.Dense(d_model, activation=None, use_bias=False)]) for _ in range(num_emb_vec) ]

        # self.embedding_ = tf.keras.layers.Embedding(target_vocab_size, d_model, mask_zero=True)
        self.embedding_ = tf.keras.layers.Dense(
            d_model, activation="relu", use_bias=False)  # only weights multiplication
        # self.pos = positional_encoding(maximum_position_encoding, d_model)
        self.pos_emb = tf.keras.layers.Embedding(
            input_dim=maximum_position_encoding, output_dim=d_model)

        self.decoder_layers = [DecoderLayer(
            d_model=d_model, num_heads=num_heads, dff=dff, dropout=dropout, norm_layer=norm_layer) for _ in range(num_layers)]

        self.dropout = tf.keras.layers.Dropout(dropout)
        self.concat = tf.keras.layers.Concatenate(axis=1)
        self.reshape_fatures = tf.keras.layers.Reshape((-1, 1, d_model))
        # self._att_weights = [[None] * len(self.decoder_layers) for _ in range (2)]

    def get_config(self):
        config = super(Decoder, self).get_config()
        config.update({
            'd_model': self.d_model,
            'feature_embedding': self.feature_embeddings,
            'embedding_': self.embedding_,
            'pos_emb': self.pos_emb,
            'decoder_layers': self.decoder_layers,
            'dropout': self.dropout,
            'concat':self.concat,
            'reshape_fatures':self.reshape_fatures,
            'norm_layer':self.norm_layer
            # 'att_weights':self._att_weights

        })
        return config

    def build(self, input_shape):
        super(Decoder, self).build(input_shape)
    def call(self, inputs, mask=None, training=None):

        feature_vec = self.feature_embeddings[0](inputs[2])
        feature_vec = tf.expand_dims(feature_vec, axis=1)
        emb = self.concat([inputs[1],feature_vec]) #appends feature vector
        
        for feature_emb in self.feature_embeddings[1:]:
            feature_vec = feature_emb(inputs[2])
            feature_vec = tf.expand_dims(feature_vec, axis=1)
            emb = self.concat([emb,feature_vec]) #appends feature vector
            

            

        x = self.embedding_(inputs[0])
        # positional encoding
        x *= tf.math.sqrt(tf.cast(self.d_model, tf.float32))

        maxlen = tf.shape(x)[1]
        positions = tf.range(start=0, limit=maxlen, delta=1)
        x += self.pos_emb(positions)
        # x += self.pos[: , :tf.shape(x)[1], :]

        x = self.dropout(x, training=training)

        # Decoder layer
        # e_mask = self.embedding_.compute_mask(inputs[0])
        # K.print_tensor(tf.shape(e_mask), message='Shape original mask')
        # K.print_tensor(e_mask, message='Value of original mask')

        embedding_mask = None
        # K.print_tensor(tf.shape(embedding_mask), message='Value of mask')

        # K.print_tensor(inputs[1], message='input1')
        # features_vec = self.reshape_fatures(feature_vec)
        # K.print_tensor(tf.shape(features_vec), message='features')

        # K.print_tensor(tf.shape(emb), message='emb')

        # self._att_weights = [[None] * len(self.decoder_layers) for _ in range (2)]
        for i,decoder_layer in enumerate(self.decoder_layers):
            # x += feature_vec

            x = decoder_layer([x, emb], mask=[embedding_mask, mask])
            # self._att_weights[0][i] = decoder_layer.multi_head_attention1.distribution
            # self._att_weights[1][i] = decoder_layer.multi_head_attention2.distribution


            # x = decoder_layer([x, inputs[1]], mask=[embedding_mask, mask])

        return x
    # @property
    # def attention_weights(self):
    #     return self._att_weights


def get_model(features_n=777, num_layers_enc=2, num_layers_dec=2,num_dense=3,dense_n=256, d_model=128, dff=512, num_heads=8,
             dropout_rate=0.1, wp_d=4,bs=32,sf=1.0,augment=0, loss="mse",
                concat_emb=False, optimizer="adam",norm_layer=True,activation="linear", max_traj_len = 100, num_emb_vec=4):


    # Size of input vocab plus start and end tokens
    input_vocab_size = wp_d
    target_vocab_size = wp_d

    traj_input = tf.keras.layers.Input(
        shape=(None, input_vocab_size), name="init_traj")
    target = tf.keras.layers.Input(
        shape=(None, target_vocab_size), name="shifted_target")
    features = tf.keras.layers.Input(shape=(features_n), name="features_input")

    encoder = Encoder(input_vocab_size, num_layers=num_layers_enc,maximum_position_encoding=max_traj_len,
                      d_model=d_model, num_heads=num_heads, dff=dff, dropout=dropout_rate,norm_layer=norm_layer)
    decoder = Decoder(target_vocab_size, num_layers=num_layers_dec,maximum_position_encoding=max_traj_len,num_emb_vec=num_emb_vec,
                      d_model=d_model, num_heads=num_heads, dff=dff, dropout=dropout_rate,norm_layer=norm_layer)

    x = encoder(traj_input)
    # , mask = encoder.compute_mask(traj_input))
    x = decoder([target, x, features])



    if concat_emb:
        maxlen = tf.shape(x)[1]
        features_vec = tf.expand_dims(features, axis=1)
        features_vec = tf.tile(features_vec, [1,maxlen,1])
        x = tf.concat([features_vec,x],-1)

    for i in range(num_dense):
        x = tf.keras.layers.Dense(dense_n, activation="relu")(x)

    x = tf.keras.layers.Dense(target_vocab_size, activation=activation)(x)

    model = tf.keras.models.Model(
        inputs=[traj_input, target, features], outputs=x)
    compile(model, optimizer=optimizer, loss=loss)
    return model

# from dtw_loss import *
def compile(model, optimizer="adam", loss="mse"):
    # optimizer = tf.keras.optimizers.Adam(1e-2, beta_1=0.9, beta_2=0.98,
    #                                      epsilon=1e-9)
    # optimizer = tf.keras.optimizers.Adam(1e-4)
    # loss = tf.keras.losses.SparseCategoricalCrossentropy(
    #     from_logits=True, reduction='none')
    # optimizer = tf.keras.optimizers.Adam()
    MSE = tf.keras.losses.MeanSquaredError()
    # MSLE = tf.keras.losses.MeanSquaredLogarithmicError()


    
    # def LDA(y_true, y_pred):

    #     alpha = 0.1
    #     epsilon = 10e-6

    #     y_true_abs = tf.norm(y_true, ord='euclidean', axis=-1)
    #     y_pred_abs = tf.norm(y_pred, ord='euclidean', axis=-1)

    #     y_true = tf.expand_dims(y_true, -1)
    #     y_pred = tf.expand_dims(y_pred, -1)

    #     y_pred  = tf.transpose(y_pred, [0, 1, 3,2])

    #     a = tf.squeeze(tf.matmul(y_pred, y_true),[2, 3])
    #     b = tf.add(epsilon,tf.multiply(y_true_abs,y_pred_abs))
    #     angle_diff = tf.add(1.0,-tf.math.divide(a,b))
    #     ld = tf.maximum(tf.square(tf.add(y_true_abs,-y_pred_abs)), 1e-9)
    #     lenght_diff = tf.math.divide(tf.math.sqrt(ld),tf.add(epsilon, tf.add(y_true_abs,y_pred_abs)))

    #     k1 = 0.5
    #     k2 = 0.5

    #     loss_lda = tf.add(tf.math.multiply(k1,lenght_diff), tf.math.multiply(k2*1/2,angle_diff))
    #     loss_mse = tf.square(y_true-y_pred)
    #     # loss_log = tf.reduce_mean(tf.square(y_true-y_pred))
    #     loss_LDA_MSE = tf.add(loss_mse, tf.math.multiply(alpha, loss_lda))
    #     return tf.reduce_mean(loss_LDA_MSE)


    def masked_loss(y_true, y_pred):
        mask = tf.math.logical_not(tf.math.equal(y_true, 0))
        _loss = loss(y_true, y_pred)

        mask = tf.cast(mask, dtype=_loss.dtype)
        _loss *= mask

        return tf.reduce_sum(_loss)/tf.reduce_sum(mask)

    # if loss == "lda" or loss == "LDA":
    #     _loss = LDA
    #     metrics = [MSE]

    # else:
    #     _loss = MSE
    #     metrics = [LDA]
    
    _loss = MSE
    metrics=[]
    # def softDTW(a, b):
    #     return batch_soft_dtw(a, b, 0.01, warp=0.0, metric="L1")

    model.compile(optimizer=optimizer, loss=_loss, metrics=metrics)


def file_name2dict(s, delimiter ="&", show=True):
    d = {}
    if s[-3:] == ".h5":
        s = s[:-3]
    for i in s.split(delimiter)[1:]:
        l = i.split(":")
        if '.' in l[1]:
            d[l[0]] = float(l[1])
        elif l[1] == "False":
            d[l[0]] = False
        elif l[1] == "True":
            d[l[0]] = True
        else:
            try:
                d[l[0]] = int(l[1])
            except:
                d[l[0]] = l[1]
    if show:
        print(d)
    return d


def load_model(model_file, model_path="models/", delimiter ="&"):
    # file nam eexample: TF&num_layers_enc:2&num_layers_dec:2&d_model:128&dff:512&num_heads:8&dropout_rate:0.1&wp_d:2.h5
    
    file_name = model_file.split("/")[-1]
    param = file_name2dict(file_name,delimiter=delimiter)
    model = get_model(**param)
    # model.load_weights(os.path.join(model_path,f))

    print("loading weights: ",model_file)
    model.load_weights(model_file)
    print("DONE")

    return model
