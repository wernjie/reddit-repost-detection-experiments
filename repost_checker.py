#!/usr/bin/env python3

import json
import random
from difflib import SequenceMatcher
from os import listdir
from os.path import isfile, join
from PIL import Image, UnidentifiedImageError
from ocr import OCR
from hasher import Hasher
from utils import generate_bad_repost

class RepostChecker:
    '''
    helper class to check reposts using all available modules

    variables that can be modified:
    - verbose      : Boolean value indicating whether verbose output is printed.
    - use_cache    : Boolean value indicating whether to read from cache if possible.
    - update_cache : Boolean value indicating whether to update the cache.
    '''

    def __init__(self, img_dir: str, imagehash_method = 'dHash'):
        '''
        Initialises the repost checker using the given image directory and image hashing method

        Parameters:
        - img_dir          : A string representing the location to read post images from. Also saves it's resulting cache data there.
        - imagehash_method : The method for hashing the image. A Hasher.ImageHashMethod enum value or its raw value string is accepted.
        '''
        self.verbose = True
        self.__imagehash_method = imagehash_method
        self.img_dir = img_dir
        self.__cache_json_path = join(img_dir, '__repost_check_data__.json')
        self.use_cache = True
        self.update_cache = True
        self.__imageToHash = {}
        self.__imageToText = {}

    def vPrint(self,x=''):
        if self.verbose:
            print(x)

    def readProcessedDataFromCache(self):
        try:
            if self.use_cache:
                with open(self.__cache_json_path, 'r', encoding='utf-8') as json_data:
                    x = json.load(json_data)
                    if 'image_to_hash' in x:
                        self.__imageToHash = x['image_to_hash']
                    if 'image_to_text' in x:
                        self.__imageToText = x['image_to_text']
        except FileNotFoundError:
            pass

    def saveProcessedDataToCache(self):
        if self.update_cache:
            output = {'image_to_hash': self.__imageToHash, 'image_to_text': self.__imageToText}
            with open(self.__cache_json_path, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=4, ensure_ascii=False)



    def processData(self):
        '''
        Processes all posts and returns two dictionaries in a tuple.
        The first maps image name to hash, and
        the second maps image name to OCR results.

        The results will also be cached in memory within the class and
        will be used in other methods for checking reposts

        Returns:
        A tuple of two dictionaries, first one containing image name to hash mappings
        and second one containing image name to OCR readings.
        '''

        files = [f for f in listdir(self.img_dir) if isfile(join(self.img_dir, f)) and not f.startswith('.')]
        files.sort()

        self.readProcessedDataFromCache()

        d = self.__imageToHash
        t = self.__imageToText

        self.vPrint("loading... " + str(len(files)) + ' items')
        for i, file in enumerate(files):
            if i % 100 == 0:
                self.vPrint('partial: %5d/%d' % (i,len(files)))

            try:
                if file not in d or file not in t:
                    img = Image.open(join(self.img_dir, file))
                    d[file] = Hasher.hashImage(img, self.__imagehash_method)
                    t[file] = OCR.read2(img)
            except KeyboardInterrupt:
                self.vPrint('skipped remaining files')
                if file in d:
                    del d[file]
                if file in t:
                    del t[file]
                break
            except UnidentifiedImageError:
                self.vPrint('skipped ' + file + ' (not an image)')
                if file in d:
                    del d[file]
                if file in t:
                    del t[file]

        self.vPrint('loaded: ' + str(len(d.items())) + ' items')
        self.__imageToHash = d
        self.__imageToText = t
        self.saveProcessedDataToCache()
        return (d,t)


    def checkRepostDetection(self, img: str, img_diff_min: int = 15, text_sim_min: float = 0.7, recheck_img: bool = True, generate_repost: bool = False, save_generated_repost: bool = True):
        '''
        Checks whether reposts can be detected correctly using
        a naive algorithm considering image hashes and ocr text.

        This assumes the dataset is correctly labelled such that
        a reposted image is the image name prefixed with _REPOST_.

        If an image is custom crafted and you don't want it to
        make a deduction of whether it's a true positive or otherwise,
        simply avoid using the standard format name of:
            <subreddit>_<postID>.<imgExtension>
        '''
        distances = []
        name_dist_dict = {}
        d = self.__imageToHash
        t = self.__imageToText

        target_check = img
        target_path = join(self.img_dir, target_check)
        self.vPrint('we\'ll process post : ' + target_check)
        if generate_repost or recheck_img:
            target_img = Image.open(target_path)
        if recheck_img or target_check not in d or target_check not in t:
            self.vPrint('computing target metadata')
            target_hash = Hasher.hashImage(target_img, self.__imagehash_method)
            target_text = OCR.read2(target_img)
            d[target_check] = target_hash
            t[target_check] = target_text
            self.__imageToHash = d
            self.__imageToText = t
        else:
            target_hash = d[target_check]
            target_text = t[target_check]


        bad_check = '_REPOST_' + target_check
        if generate_repost:
            self.vPrint('generating dummy repost : _REPOST_' + target_check)
            bad_img = generate_bad_repost(target_path)
            bad_img_path = join(self.img_dir, bad_check)
            self.vPrint('computing target metadata')
            bad_img_hash = Hasher.hashImage(bad_img, self.__imagehash_method)
            bad_img_text = OCR.read2(bad_img)
            d[bad_check] = bad_img_hash
            t[bad_check] = bad_img_text
            if save_generated_repost:
                bad_img.save(bad_img_path)
                self.__imageToHash = d
                self.__imageToText = t

        if self.update_cache:
            self.saveProcessedDataToCache()


        self.vPrint('\nchecking...')

        for key, value in d.items():
            img_diff = Hasher.diff(value, target_hash, 'IMAGE')
            text_sim = SequenceMatcher(None, t[key] if key in t else '', target_text).ratio()
            distances.append \
            ( \
                (key, \
                 img_diff, \
                 text_sim)
            )
            name_dist_dict[key] = (distances[-1][1], distances[-1][2])


        def orderOfSort(x):
            '''dynamic sorting to prioritise text if image and text are both really close'''
            img_diff = x[1]
            txt_diff = 1-x[2]
            if txt_diff <= 1-text_sim_min and img_diff <= img_diff_min:
                return (txt_diff, img_diff)
            return (img_diff, txt_diff)

        distances.sort(key=orderOfSort)
        counter = 0

        results = {}
        FP = 0
        FN = 0


        self.vPrint('--- similar results ---')
        self.vPrint('  SAME?  | IMG_DIFF | TEXT_SIM | IMAGE')
        for a,b,c in distances:
            standardFormat = len(a.split('.')) == 2 and len(a.split('.')[0].replace('_REPOST_', '').split('_')) == 2
            is_known_same = a.replace('_REPOST_','') == target_check.replace('_REPOST_', '')
            is_repost = b <= img_diff_min and c >= text_sim_min
            if not standardFormat:
                validity = '??'
                if is_known_same:
                    if is_repost:
                        validity = 'TP'
                    else:
                        validity = 'FN'
                        FN += 1
            elif is_repost:
                if is_known_same:
                    validity = 'TP'
                else:
                    validity = 'FP'
                    FP += 1
            else:
                if is_known_same:
                    validity = 'FN'
                    FN += 1
                else:
                    validity = 'TN'

            if counter < 10:
                counter += 1
                if self.verbose:
                    self.vPrint('%8s   %8d   %8.3f    %-50s' % \
                                (('YES, ' if is_repost else ' NO, ') + validity,b,c,a))

                    if standardFormat:
                        subreddit = a.split('_')[0]
                        if subreddit == "" and a.split('_')[1] == 'REPOST':
                            subreddit = a.split('_')[2]
                        post_id = a.split('_')[-1].split('.')[0]
                        self.vPrint('reddit.com/r/' + subreddit + '/comments/' + post_id + '/')
                    else:
                        self.vPrint('• this image isn\'t from the standard dataset')

                    if a == target_check:
                        self.vPrint('• this is the originally chosen image')
                    elif is_known_same:
                        self.vPrint('• this is a known to be the same as the chosen image')
                    self.vPrint()

            results[a] = {
                'imgName': a,
                'isRepost': is_repost,
                'validity': validity,
                'imgDiff': b,
                'textSim': c
            }

        if FP or FN:
            self.vPrint('important notes:')
            self.vPrint('we have %d known false positives and %d known false negatives for this\n' % (FP, FN))

        return results

    def listRepostsOf(self, img: str):
        '''lists detected reposts for the given image name in the image directory'''
        detection = self.checkRepostDetection(img, generate_repost=False)
        data = []
        for key, value in detection.items():
            if value['isRepost'] and key != img:
                data.append(key)
        return data

    def generateRepostsForAll(self):
        '''generates reposts for every single non repost image in the image directory'''
        names = list(filter(lambda x: '_REPOST_' not in x, self.__imageToHash.keys()))
        self.vPrint('generating ' + str(len(names)) + ' reposts')
        try:
            for i, name in enumerate(names):
                repname = '_REPOST_' + name
                if repname in self.__imageToHash and repname in self.__imageToText:
                    continue
                if i % 10 == 0:
                    self.vPrint('partial: %5d/%d' % (i,len(names)))
                target_path = join(self.img_dir, name)
                bad_img = generate_bad_repost(target_path)
                bad_img_hash = Hasher.hashImage(bad_img, self.__imagehash_method)
                bad_img_text = OCR.read2(bad_img)
                self.__imageToHash[repname] = bad_img_hash
                self.__imageToText[repname] = bad_img_text
                bad_img.save(join(self.img_dir, repname))
            self.vPrint('done!')
        except KeyboardInterrupt:
            self.vPrint('interrupted')
        finally:
            self.saveProcessedDataToCache()


    def findDetectionRate(self, imgs: list = [], sample_count: int = None, seed: int = None, img_diff_min: int = 15, text_sim_min: float = 0.7):
        '''finds the repost detection rate (precision, recall, true/false positives/negatives)'''

        vC = {'TP':0,'FP':0,'TN':0,'FN':0,'??':0}
        names = imgs if imgs else list(self.__imageToHash.keys())
        if seed:
            random.seed(seed)
        random.shuffle(names)

        interrupted = False
        v = self.verbose
        self.verbose = False
        c = self.update_cache
        self.update_cache = False

        try:
            total = min(len(names), sample_count) if sample_count else len(names)
            for i, img in enumerate(names):
                if sample_count and i >= sample_count:
                    break
                res = self.checkRepostDetection(img, img_diff_min=img_diff_min, text_sim_min=text_sim_min, recheck_img=False, generate_repost=False)
                for _, data in res.items():
                    vC[data['validity']] += 1
                if v:
                    try:
                        precision = round(vC['TP']/(vC['TP'] + vC['FP'])*100, 1)
                        recall    = round(vC['TP']/(vC['TP'] + vC['FN'])*100, 1)
                    except ZeroDivisionError:
                        precision = 0
                        recall    = 0
                    print('\n[%5d/%-5d] %s' % \
                          (i+1, total, img))
                    print('  ~> (precision: %5.1f%%, recall: %5.1f%%) %s' % \
                          (precision, recall, str(vC)))
        except KeyboardInterrupt:
            interrupted = True
            if v:
                print('keyboard interrupt received, skipping remaining tests')
        finally:
            self.verbose = v
            self.update_cache = c
            self.saveProcessedDataToCache()

        precision = round(vC['TP']/(vC['TP'] + vC['FP']),3)
        recall    = round(vC['TP']/(vC['TP'] + vC['FN']),3)

        if v:
            print()
            if sample_count or interrupted:
                print('-- results (sample count) --')
            else:
                print('-- results --')
            print('precision : %4.1f%%' % (precision*100))
            print('recall    : %4.1f%%' % (recall*100))
            print('stats     : %s' % str(vC))
            print()

        vC['precision'] = round(precision, 3)
        vC['recall'] = round(recall,3)

        return vC

if __name__ == '__main__':
    repostChecker = RepostChecker('scraper_cache')
    print('this test script is for testing simple repost detection via image hashing and ocr capabilities')
    print('processing images in scraper_cache...')
    repostChecker.processData()
    print('done!')
    print('would you like to check repost detection for individual images now? [y/N]')
    if input().lower().startswith('y'):
        while True:
            try:
                print('type an image name in scraper_cache! (ctrl-c to exit)')
                imgName = input()
                print('generate a repost with prefix _REPOST_? [y/N]')
                shdRepost = input().lower().startswith('y')
                _ = repostChecker.checkRepostDetection(imgName, generate_repost=shdRepost)
            except KeyboardInterrupt:
                break
            except:
                print('something was wrong.')
                continue

    print()
    print('-'*30)
    print('''
if you\'re in an interactive shell,
try the following examples:

    # get other image names flagged as reposts of the given image name
    res = repostChecker.listRepostsOf(imageName)

    # get detailed detection results of this particular image against all images
    res = repostChecker.checkRepostDetection(imageName[, options])

    # finds detection rate w/ all images against all images
    res = repostChecker.findDetectionRate()

    # find detection rate w/ 100 random images against all images
    res = repostChecker.findDetectionRate(sample_count=100)

    # find detection rate w/ 100 random images against all images,
    # using seed 69 (so we can repeat using the same 100 random images later),
    # given positive result refers to image difference of 15 or less,
    # and text similarity of 60% or higher
    res = repostChecker.findDetectionRate(sample_count=100, seed=69, img_diff_min=15, text_sim_min=0.6)
''')
