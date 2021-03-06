import sys
import json
import torch
import numpy as np
import argparse
import torchvision.transforms as transforms
import cv2
from DRL.ddpg import decode
from utils.util import *
from PIL import Image
from torchvision import transforms, utils
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

aug = transforms.Compose(
            [transforms.ToPILImage(),
             transforms.RandomRotation(degrees=180, fill=(255, 255, 255)),
             ])

width = 256
# convas_area = width * width

img_train = []
img_test = []
vol_train = []
vol_test = []
train_num = 0
test_num = 0

class Paint:
    def __init__(self, batch_size, max_step):
        self.batch_size = batch_size
        self.max_step = max_step
        self.action_space = (13)
        self.observation_space = (self.batch_size, width, width, 7)
        self.test = False
        
    def load_data(self):
        # CelebA
        global train_num, test_num
        for i in range(200):
            img_id = '%05d' % (i + 1)
            try:
                img = cv2.imread('/vinbrain/quantm/cartoon/target/cartoonset10k_' + img_id + '.png', cv2.IMREAD_COLOR)
                # vol = cv2.imread('/vinbrain/quantm/cartoon/volume/cartoonset10k_' + img_id + '.png', cv2.IMREAD_COLOR)
                img = cv2.resize(img, (width, width), interpolation=cv2.INTER_NEAREST)
                # vol = cv2.resize(vol, (width, width), interpolation=cv2.INTER_NEAREST)
                if i >= 100:                
                    train_num += 1
                    img_train.append(img)
                    # vol_train.append(vol)
                else:
                    test_num += 1
                    img_test.append(img)
                    # vol_test.append(vol)
            finally:
                if (i + 1) % 100 == 0:                    
                    print('loaded {} images'.format(i + 1))
        print('finish loading data, {} training images, {} testing images'.format(str(train_num), str(test_num)))
        
    def pre_data(self, id, test):
        if test:
            img = img_test[id]
            # vol = vol_test[id]
        else:
            img = img_train[id]
            # vol = vol_train[id]
        # if not test:
        img = aug(img)
        # vol = aug(vol)
        img = np.asarray(img)
        # vol = np.asarray(vol)
        vol = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)[:,:,np.newaxis]
        # print(img.shape, vol.shape)
        return np.transpose(vol, (2, 0, 1)), np.transpose(img, (2, 0, 1))
    
    def reset(self, test=False, begin_num=False):
        self.test = test
        self.imgid = [0] * self.batch_size
        self.gt = torch.zeros([self.batch_size, 3, width, width], dtype=torch.uint8).to(device)
        self.vol = torch.zeros([self.batch_size, 1, width, width], dtype=torch.uint8).to(device)
        for i in range(self.batch_size):
            if test:
                id = (i + begin_num)  % test_num
            else:
                id = np.random.randint(train_num)
            self.imgid[i] = id
            # self.gt[i] = torch.tensor(self.pre_data(id, test))
            tmp_vol, tmp_gt = self.pre_data(id, test)
            self.vol[i] = torch.tensor(tmp_vol)
            self.gt[i] = torch.tensor(tmp_gt)
        self.tot_reward = ((self.gt.float() / 255 - self.vol.float() / 255) ** 2).mean(1).mean(1).mean(1)
        self.stepnum = 0
        # self.canvas = torch.zeros([self.batch_size, 3, width, width], dtype=torch.uint8).to(device)
        self.canvas = torch.cat([self.vol, self.vol, self.vol], axis=1).to(device)
        self.lastdis = self.ini_dis = self.cal_dis()
        return self.observation()
    
    def observation(self):
        # canvas B * 3 * width * width
        # gt B * 3 * width * width
        # T B * 1 * width * width
        ob = []
        T = torch.ones([self.batch_size, 1, width, width], dtype=torch.uint8) * self.stepnum
        # return torch.cat((self.canvas, self.gt, T.to(device)), 1) # canvas, img, T
        return torch.cat((self.vol, self.canvas, self.gt, T.to(device)), 1) # volume, canvas, img, T

    def cal_trans(self, s, t):
        return (s.transpose(0, 3) * t).transpose(0, 3)
    
    def step(self, action):
        # self.canvas = (decode(action, self.canvas.float() / 255) * 255).byte()
        # Decode action to value assignment
        self.canvas = decode(action, self.vol, self.canvas)
        self.stepnum += 1
        ob = self.observation()
        done = (self.stepnum == self.max_step)
        reward = self.cal_reward() # np.array([0.] * self.batch_size)
        return ob.detach(), reward, np.array([done] * self.batch_size), None

    def cal_dis(self):
        return (((self.canvas.float() - self.gt.float()) / 255) ** 2).mean(1).mean(1).mean(1)
    
    def cal_reward(self):
        dis = self.cal_dis()
        reward = (self.lastdis - dis) / (self.ini_dis + 1e-8)
        self.lastdis = dis
        return to_numpy(reward)
