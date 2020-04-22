import itertools
import logging
from abc import abstractmethod

import numpy as np
from keras.preprocessing.image import ImageDataGenerator

from loaders import loader_factory
from model_tester import ModelTester

log = logging.getLogger('executor')


class Executor(object):
    """
    Base class for executor objects.
    """
    def __init__(self, conf, model):
        self.conf = conf
        self.model = model
        self.loader = loader_factory.init_loader(self.conf.dataset_name)
        self.batch = 0
        self.epoch = 0

    @abstractmethod
    def init_train_data(self):
        pass

    @abstractmethod
    def get_loss_names(self):
        pass

    @abstractmethod
    def train(self):
        pass

    def get_data_generator(self, train_images=None, train_labels=None):
        """
        Create a data generator that also augments the data.
        :param train_images: input data
        :param train_labels: target data
        :return              an iterator that gives a tuple of (input, output) data.
        """
        image_dict = self.get_datagen_params(augment_intensity=True)
        mask_dict  = self.get_datagen_params(augment_intensity=False)

        img_gens = []
        if train_images is not None:
            if type(train_images) != list:
                train_images = [train_images]

            for img_array in train_images:
                img_gens.append(ImageDataGenerator(**image_dict).flow(img_array, batch_size=self.conf.batch_size,
                                                                      seed=self.conf.seed))

        msk_gens = []
        if train_labels is not None:
            if type(train_labels) != list:
                train_labels = [train_labels]

            for msk_array in train_labels:
                msk_gens.append(ImageDataGenerator(**mask_dict).flow(msk_array, batch_size=self.conf.batch_size,
                                                                     seed=self.conf.seed))

        if len(img_gens) > 0 and len(msk_gens) > 0:
            all_data = img_gens + msk_gens
            gen = itertools.zip_longest(*all_data)
            return gen
        elif len(img_gens) > 0 and len(msk_gens) == 0:
            if len(img_gens) == 1:
                return img_gens[0]
            return itertools.zip_longest(*img_gens)
        elif len(img_gens) == 0 and len(msk_gens) > 0:
            if len(msk_gens) == 1:
                return msk_gens[0]
            return itertools.zip_longest(*msk_gens)
        else:
            raise Exception("No data to iterate.")

    def validate(self, epoch_loss):
        pass

    def add_residual(self, data):
        residual = np.ones(data.shape[:-1] + (1,))
        for i in range(data.shape[-1]):
            residual[data[..., i:i+1] == 1] = 0
        return np.concatenate([data, residual], axis=-1)

    @abstractmethod
    def test(self):
        """
        Evaluate a model on the test data.
        """
        log.info('Evaluating model on test data')
        tester = ModelTester(self.model, self.conf)
        tester.run()

    def stop_criterion(self, es, logs):
        es.on_epoch_end(self.epoch, logs)
        if es.stopped_epoch > 0:
            return True

    def get_datagen_params(self, augment_intensity=False):
        """
        Construct a dictionary of augmentations.
        :return: a dictionary of augmentation parameters to use with a keras image processor
        """
        d = dict(horizontal_flip=False, vertical_flip=False, rotation_range=20.,
                 width_shift_range=0, height_shift_range=0, zoom_range=0) #, fill_mode='constant', cval=-2)

        # only apply intensity augmentations to images
        # brightness_range rescales images to 0-255. Ensure they are mapped back to -1 and 1.
        # if augment_intensity:
        # #     d['brightness_range'] = (0.95, 1.05)
        #     d['preprocessing_function'] = image_utils.intensity_augmentation # add_gaussian_noise # or data_utils.normalise
        return d

    def align_batches(self, array_list):
        """
        Align the arrays of the input list, based on batch size.
        :param array_list: list of 4-d arrays to align
        """
        mn = np.min([x.shape[0] for x in array_list])
        new_list = [x[0:mn] + 0. for x in array_list]
        return new_list

    def get_fake(self, pred, fake_pool, sample_size=-1):
        sample_size = self.conf.batch_size if sample_size == -1 else sample_size

        if pred.shape[0] > 0:
            fake_pool.extend(pred)

        fake_pool = fake_pool[-50:]
        sel = np.random.choice(len(fake_pool), size=(sample_size,), replace=False)
        fake_A = np.array([fake_pool[ind] for ind in sel])
        return fake_pool, fake_A