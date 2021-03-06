# VAE Spiral Keras
from keras.layers import Input, Dense, Lambda, BatchNormalization
from keras.models import Model
from sklearn import cluster, datasets, mixture

import numpy as np
import matplotlib.pyplot as plt
import keras.backend as K
from keras import losses
import keras

mini_batch_size = 100
n_z = 2
n_epoch = 150
nb_hidden_unit = 256
data_number = 5000
learning_rate = 0.0002
kl_introduction_proportion = 800


def getSamples(n):
    # generate vector of random angles
    angles = np.random.uniform(-np.pi, np.pi, n)

    # generate matrix of x and y coordinates
    x = np.cos(angles)
    y = np.sin(angles)
    return angles, x, y


angles, x_pos, y_pos = getSamples(data_number)
# Scale and translate position to conform with sigmoid layer
pos_arr = (np.array([x_pos, y_pos]).T)
x_train = (pos_arr[int(-data_number * 0.9):])
x_test = (pos_arr[int(data_number * 0.1):])

# Q(z|X) -- encoder
inputs = Input(shape=(2, ))
input_norm = BatchNormalization(axis=1)(inputs)
h_q = Dense(nb_hidden_unit, activation='relu')(input_norm)
h_q_norm = keras.layers.BatchNormalization(axis=1)(h_q)
# h_q_2 = Dense(nb_hidden_unit, activation='relu')(h_q_norm)
# h_q_2_norm = keras.layers.BatchNormalization(axis=1)(h_q)
mu = Dense(n_z, activation='linear')(h_q_norm)
log_sigma = Dense(n_z, activation='linear')(h_q_norm)


def sample_z(args):
    mu, log_sigma = args
    eps = K.random_normal(shape=(mini_batch_size, n_z), mean=0., stddev=1.)
    return mu + K.exp(log_sigma / 2) * eps


# Sample z ~ Q(z|X)
z = Lambda(sample_z)([mu, log_sigma])

# P(X|z) -- decoder
normalize_z = keras.layers.BatchNormalization(axis=1)
decoder_hidden = Dense(nb_hidden_unit, activation='relu')
decoder_hidden_norm = keras.layers.BatchNormalization(axis=1)
# decoder_hidden_2 = Dense(nb_hidden_unit, activation='relu')
# decoder_hidden_2_norm = keras.layers.BatchNormalization(axis=1)
decoder_mu = Dense(2, activation='linear')
decoder_sigma = Dense(2, activation='linear')

norm_z = normalize_z(z)
h_p = decoder_hidden(norm_z)
h_p_norm = decoder_hidden_norm(h_p)
# h_p_2 = decoder_hidden_2(h_p_norm)
# h_p_2_norm = decoder_hidden_2_norm(h_p_2)
mu_decoder = decoder_mu(h_p_norm)
std_decoder = decoder_sigma(h_p_norm)

alpha = K.variable(1.)

# Overall VAE model, for reconstruction and training
vae = Model(inputs, mu_decoder)
vae.summary()
# Encoder model, to encode input into latent variable
# We use the mean as the output as it is the center point, the representative of the gaussian
encoder = Model(inputs, mu)

# Generator model, generate new data given latent variable z
d_in = Input(shape=(n_z, ))
d_in_norm = normalize_z(d_in)
d_h = decoder_hidden(d_in_norm)
d_h_norm = decoder_hidden_norm(d_h)
# d_h_2 = decoder_hidden_2(d_h_norm)
# d_h_2_norm = decoder_hidden_2_norm(d_h_2)
d_out = decoder_mu(d_h_norm)
d_std_out = decoder_sigma(d_h_norm)

decoder = Model(d_in, [d_out, d_std_out])


def vae_loss(y_true, y_pred):
    """ Calculate loss = reconstruction loss + KL loss for each data in minibatch """
    # E[log P(X|z)] here a Gaussian BCE
    recon = -K.log(2 * np.pi) - 0.5 * K.sum(
        std_decoder, axis=1) - 0.5 * K.sum(
            (K.square(inputs - mu_decoder) / (K.exp(std_decoder))), axis=1)

    # D_KL(Q(z|X) || P(z|X)); calculate in closed form as both dist. are Gaussian
    kl_loss = 0.5 * (
        K.sum(1 + log_sigma - K.square(mu) - K.exp(log_sigma), axis=1))
    return -K.mean(alpha * kl_loss + recon, axis=0)


def kl_loss(y_true, y_pred):
    kl_loss = 0.5 * (
        K.sum(1 + log_sigma - K.square(mu) - K.exp(log_sigma), axis=1))
    return -K.mean(alpha * kl_loss, axis=0)


def loss_recon(y_true, y_pred):
    recon = -K.log(2 * np.pi) - 0.5 * K.sum(
        std_decoder, axis=1) - 0.5 * K.sum(
            (K.square(inputs - mu_decoder) / (K.exp(std_decoder))), axis=1)
    return -K.mean(recon, axis=0)


# Callback function
class LossHistory(keras.callbacks.Callback):
    def __init__(self, alpha):
        self.alpha = alpha

    def on_train_begin(self, logs={}):
        print("Begin Training")
        self.losses = []
        self.losses_recon = []
        self.losses_kl = []

    def on_epoch_end(self, epoch, logs={}):
        self.losses.append(logs.get('loss'))
        self.losses_recon.append(logs.get('loss_recon'))
        self.losses_kl.append(logs.get("kl_loss"))

        # Alpha is a regularizer to slow down learning at the beginning
        K.set_value(self.alpha,
                    np.min([kl_introduction_proportion,
                            (epoch)]) / (kl_introduction_proportion))
        print("Alpha:", K.get_value(alpha))

    def on_train_end(self, logs=None):
        line_kl_recon, = plt.plot(
            self.losses[5:], label="KL + Reconstruction loss")
        #print(self.losses_kl)
        line_kl, = plt.plot(self.losses_kl[5:], label="KL loss")
        line_recon, = plt.plot(
            self.losses_recon[5:], label="Reconstruction loss")
        plt.ylabel('Loss')
        plt.xlabel('Epoch')

        plt.legend(handles=[line_kl_recon, line_kl, line_recon])

        plt.plot(self.losses_recon)

        plt.show()


history = LossHistory(alpha)

optimizer = keras.optimizers.rmsprop(lr=learning_rate)
vae.compile(optimizer, vae_loss, metrics=[kl_loss, loss_recon])
# vae.compile(optimizer,loss='binary_crossentropy')
vae.fit(
    x_train,
    x_train,
    batch_size=mini_batch_size,
    epochs=n_epoch,
    callbacks=[history],
    shuffle=True)

#####################################################
### Visualise
#####################################################

# Encode datapoints
means = encoder.predict(x_test)
plt.figure()
plt.title('Encoded means')
plt.ylabel('z2')
plt.xlabel('z1')
plt.scatter(means[:, 0], means[:, 1], s=0.5, alpha=0.5)

# Decode means
[decoded_mean, decoded_variance] = decoder.predict(means)
plt.figure()
plt.title('Reconstructed means')
plt.ylabel('x2')
plt.xlabel('x1')
plt.scatter(decoded_mean[:, 0], decoded_mean[:, 1], s=0.5, c="red")

# Generate random points
plt.figure()
plt.title('Random point generation from random latent space')
plt.ylabel('x2')
plt.xlabel('x1')

random_means = np.random.normal(loc=0, scale=1.0, size=[10000, 2])
[decoded_random_means,
 decoded_random_variances] = decoder.predict(random_means)

decoded_random = decoded_random_means + np.exp(
    decoded_random_variances / 2) * np.random.normal(
        loc=0, scale=1.0, size=[10000, 2])
plt.scatter(decoded_random[:, 0], decoded_random[:, 1], s=0.5, c="orange")
plt.show()