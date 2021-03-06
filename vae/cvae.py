from keras.layers import Input, Dense, Lambda, Concatenate, BatchNormalization, PReLU
from keras.layers.merge import concatenate
from keras.models import Model, Sequential, load_model
from keras.utils import plot_model, to_categorical
from keras import backend as K
from keras import metrics, losses
from keras.callbacks import TensorBoard
from datetime import datetime


class CVAE():
    def __init__(self,
                 input_size,
                 label_size,
                 latent_size,
                 d_layers,
                 optimizer='rmsprop',
                 show_metrics=False,
                 batch_norm=True):
        # variables
        self.input_size = input_size
        self.label_size = label_size
        self.latent_size = latent_size
        self.layer_sizes = d_layers
        self.batch_norm = batch_norm

        # Build inputs tensor containing the input data and conditional array
        self.input = Input(shape=(input_size, ), name="input_data")
        self.conditional = Input(shape=(label_size, ), name="input_labels")
        self.inputs = concatenate([self.input, self.conditional])

        # Build encoder and decoder
        self.mu, self.log_sigma = self.create_encoder(self.inputs)
        self.decoder = self.create_decoder()
        self.sampler = self.decoder([Lambda(self.sample_z)([self.mu, self.log_sigma]), self.conditional])

        # Generate Keras models for the encoder and the entire VAE
        self.encoder = Model([self.input, self.conditional], self.mu)
        self.model = Model([self.input, self.conditional], self.sampler)
        self.optimizer = optimizer
        self.verbose = show_metrics
        self.callbacks = []

        # Run some post operations
        self.init_callbacks()

    # returns two tensors, one for the encoding (z_mean), one for making the manifold smooth
    def create_encoder(self, nn_input):
        x = nn_input
        for l in self.layer_sizes:
            x = Dense(l, activation="relu", name="h_enc_{}".format(l))(x)
            if self.batch_norm:
                x = BatchNormalization()(x)
        z_mu = Dense(self.latent_size, activation="linear", name="z_mean")(x)
        z_log_sigma = Dense(self.latent_size, activation="linear", name="z_log_sigma")(x)
        return z_mu, z_log_sigma

    def create_decoder(self):
        noise = Input(shape=(self.latent_size,))
        label = Input(shape=(self.label_size,))
        x = concatenate([noise, label])
        for l in self.layer_sizes[::-1]:
            x = Dense(l, activation='relu')(x)
            if self.batch_norm:
                x = BatchNormalization()(x)

        out = Dense(self.input_size, activation='linear')(x)

        return Model([noise, label], out)

    def create_decoder_(self):
        z = Lambda(self.sample_z)([self.mu, self.log_sigma])
        z_cond = concatenate([z, self.conditional])
        layers = self.layer_sizes[::-1]
        # Build sampler (for training) and decoder at the same time.
        ae_output = z_cond
        inpt = Input(shape=(self.latent_size+self.label_size, ), name="decoder_input")
        dec_tensor = inpt
        for l in layers:
            dec = Dense(l, activation='relu', name="h_dec_{}".format(l))
            ae_output = dec(ae_output)
            dec_tensor = dec(dec_tensor)
            if self.batch_norm:
                ae_output = BatchNormalization()(ae_output)
                dec_tensor = BatchNormalization()(dec_tensor)

        # We use linear activation to accommodate real valued output data
        output_layer = Dense(self.input_size, activation="linear", name="output")
        ae_output = output_layer(ae_output)
        dec_tensor = output_layer(dec_tensor)

        # dec_tensor is used to create a separate decoder model used for generation
        # ae_output will be used in the __init__ to create the full CVAE model
        decoder = Model(inpt, dec_tensor)
        return ae_output, decoder

    # used for training
    def sample_z(self, args):
        z_mean, z_log_var = args
        epsilon = K.random_normal(
            shape=(K.shape(z_mean)[0], K.int_shape(z_mean)[1]),
            mean=0.,
            stddev=1.0)
        return z_mean + K.exp(z_log_var / 2) * epsilon

    # loss functions
    def vae_loss(self, x, x_decoded_mean):
        xent_loss = self.reconstruction_loss(x, x_decoded_mean)
        kl_loss = self.kl_loss(x, x_decoded_mean)
        return K.mean(xent_loss + kl_loss)

    def reconstruction_loss(self, x, x_decoded_mean):
        return losses.mean_squared_error(x, x_decoded_mean)

    def kl_loss(self, x, x_decoded_mean):
        return (0.5 * K.sum(
            K.exp(self.log_sigma) + K.square(self.mu) - 1. - self.log_sigma,
            axis=-1))

    # builds and returns the model. This is how you get the model in your training code.
    def compile(self):
        met = []
        if self.verbose:
            met = [self.reconstruction_loss, self.kl_loss]
        self.model.compile(self.optimizer, loss=self.vae_loss, metrics=met)
        return self.model

    def load_model(self, path):
        return load_model(path)

    def init_callbacks(self):
        # We store the runs in subdirectories named by the time
        dirname = datetime.now().strftime("%Y_%m_%d__%H_%M_%S")
        self.callbacks.append(
            TensorBoard(log_dir="./logs/{}/".format(dirname)))
        return None


if __name__ == "__main__":
    cvae = CVAE(784, 10, 2, [128, 64], optimizer='rmsprop')
