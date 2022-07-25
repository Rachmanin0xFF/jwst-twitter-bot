# Sorry to anyone reading this; I haven't had the time to clean up and comment this code yet.
# I'll move this all to GCP or something eventually, but right now it's just running on my home desktop.
# Need to figure out how to make it use less RAM... requires at least 16GB to run right now!

# (some of these arrays are >6GB)

from astropy.io import fits
from astroquery.mast import Observations
import astroquery.exceptions
from astropy.time import Time
from astropy.io import fits
from astropy.table import vstack, Table
import numpy as np
import logging
import pathlib
import scipy.stats
import os
from PIL import Image
import shutil
from io import BytesIO
import configparser
import tweepy
import pathlib
import pickle
import PIL
from PIL import ImageFont
from PIL import ImageDraw 
from PIL import ImageOps
from time import strftime
from time import gmtime
import time
PIL.Image.MAX_IMAGE_PIXELS = None

#============================ Logging & Presistent Memory ============================#
#logging.basicConfig(filename='log.txt', encoding='utf-8', level=logging.DEBUG)
def print_info(s):
    print(s)
    #logging.info(s)
    pass
def print_debug(s):
    print(s)
    #logging.debug(s)
    pass
ctime = Time.now()
print_info("New run at " + str(ctime))
def save_null_set(path):
    with open(path,'wb') as f:
        pickle.dump({"nothin"}, f)
def save_set(s, path):
    with open(path,'wb') as f:
        pickle.dump(s, f)
def load_set(path):
    try: 
        with open(path,'rb') as f:
            my_set = pickle.load(f)
            return my_set
    except FileNotFoundError:
        return set()

#============================ Twitter Stuff ============================#

config = configparser.ConfigParser()
config.read(str(pathlib.Path(__file__).parent.resolve()) + '\\config.ini')

consumer_key = config['twitter']['consumer_key']
consumer_key_secret = config['twitter']['consumer_key_secret']

access_token = config['twitter']['access_token']
access_token_secret = config['twitter']['access_token_secret']

auth=tweepy.OAuthHandler(consumer_key,consumer_key_secret)
auth.set_access_token(access_token,access_token_secret)
api=tweepy.API(auth, wait_on_rate_limit=True, wait_on_rate_limit_notify=True) # USE TWEEPY'S RATE LIMIT!

def post_images(paths, description="test image"):
    media_ids = []
    for x in paths:
        res = api.media_upload(x)
        media_ids.append(res.media_id)
        if len(media_ids) == 4:
            break
    status = api.update_status(status=description, media_ids=media_ids)
    print_info("Posted status, output follows:")
    print_info(str(status))
    time.sleep(40) # WAIT FORTY SECONDS TO ENSURE WE DON'T EXCEED TWITTER'S 300 POST / 3HRS MAXIMUM
                   # This code is (and will remain) single-threaded, so I don't have to worry about overlapping calls.

#============================ MAST Download ============================#

obj_data = {}

ctime = Time.now()
print_info("New run at " + str(ctime))
def get_good_products_from(start_time, end_time):
    print_info("querying MAST from " + str(start_time) + " to " + str(end_time))
    obsByName = Observations.query_criteria(obs_collection="JWST",
                                            instrument_name=["NIRCAM","MIRI"],
                                            t_min=[start_time, end_time],
                                            calib_level=3)
    all_result_count = len(obsByName)
    obsByName = obsByName[(obsByName["dataRights"]=="PUBLIC")]
    print_debug("Number of public results from JWST NIRCAM/MIRI: " + str(len(obsByName)))
    print_debug("Number of exclusive/restricted results: " + str(all_result_count-len(obsByName)))
    print_debug(obsByName[:4])

    for o in obsByName:
        obj_data[o["obs_id"]] = o
    alli2d = []
    k = 0
    for o in obsByName:
        k += 1
        print_debug("Opening object " + str(k) + "/" + str(len(obsByName)))
        try:
            data_products = None
            while data_products is None:
                try:
                    data_products = Observations.get_product_list(o)
                except OSError:
                    data_products = None

            calibrated = data_products[(data_products['calib_level'] >= 3)]
            print_debug("Total calib_level=3 products in objects:" + str(len(calibrated)))
            i2d = calibrated[(calibrated["productSubGroupDescription"] == "I2D")]
            print_debug("Total calib_level=3 && I2D products in result:" + str(len(i2d)))
            alli2d.append(i2d)
        except astroquery.exceptions.InvalidQueryError:
            pass
    if len(alli2d)==0:
        return Table({})
    else:
        return vstack(alli2d)

def download(products):
    keko = None
    while True:
        try: 
            keko = Observations.download_products(products, mrp_only=True)
            break
        except OSError:
            print_info('SSL CONNECTION INTERRUPTED')
    return keko

def get_product_filenames(products):
    return [x["productFilename"] for x in products]

#============================ Image Processing ============================#

def smootherstep(x):
    return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)
def to1(x):
    return 0.5+(2.0*x-2.0)/(2*np.sqrt((2.0*x-2.0)*(2.0*x-2.0)+1.0))
def mean_ad(data):
    return np.mean(np.absolute(data - np.mean(data)))
def trim_ends(data, cutoff):
    cth = np.quantile(data, cutoff)
    ctl = np.quantile(data, 1.0-cutoff)
    f1 = data[data < cth]
    return f1[f1 > ctl]
def expand_highs(x):
    return np.piecewise(x, [x <= 0.9, x > 0.9], [lambda x: x*0.8/0.9, lambda x: 100.0/9.0*(x-0.9)**2 + 0.8*x/0.9])


def image_histogram_equalization(image, number_bins=10000):
    # from http://www.janeriksolem.net/histogram-equalization-with-python-and.html

    # get image histogram
    image_histogram, bins = np.histogram(image.flatten(), number_bins, density=True)
    cdf = image_histogram.cumsum() # cumulative distribution function
    cdf = cdf / cdf[-1] # normalize

    # use linear interpolation of cdf to find new pixel values
    image_equalized = np.interp(image.flatten(), bins[:-1], cdf)

    return image_equalized.reshape(image.shape)

def level_adjust(fits_arr):
    hist_dat = fits_arr.flatten()
    hist_dat = hist_dat[np.nonzero(hist_dat)]
    zeros = np.abs(np.sign(fits_arr))
    x0 = np.median(hist_dat)
    r = scipy.stats.median_abs_deviation(hist_dat)
    s = np.std(hist_dat)
    t = mean_ad(hist_dat)
    minval = np.quantile(hist_dat, 0.03)
    maxval = np.quantile(hist_dat, 0.98)
    rescaled = (fits_arr-minval)/(maxval-minval)
    #adjusted = (pow((pow(rescaled, 1.8)*1.4 + pow(image_histogram_equalization(rescaled), 8.0))/2.8, 0.75) - 7.0/255.0)*1.029
    #adjusted = (pow(to2(rescaled), 2.0) + pow(image_histogram_equalization(rescaled), 8.0))/2.0
    rescaled_no_outliers = np.maximum(rescaled, np.quantile(rescaled, 0.002))
    rescaled_no_outliers = np.minimum(rescaled_no_outliers, np.quantile(rescaled_no_outliers, 1.0-0.002))
    img_eqd = image_histogram_equalization(rescaled_no_outliers)
    img_eqd = (pow(img_eqd, 4.0) + pow(img_eqd, 8.0) + pow(img_eqd, 16.0))/3.0
    adjusted = expand_highs((img_eqd + to1(rescaled))*0.5)
    return np.clip(adjusted*zeros, 0.0, 1.0)

font = ImageFont.truetype("PTMono-Regular.ttf", 14)

def add_text(path_in, path_out, text):
    try:
        os.remove(path_out)
    except FileNotFoundError:
        pass
    with Image.open(path_in) as img_in:
        drawt = ImageDraw.Draw(img_in)
        txw = drawt.textbbox((5, 5), text, font=font)[2] + 5 # x0 y0 x1 y1
        new_size = (max(img_in.size[0], txw), np.round(img_in.size[1]+160).astype(np.int64))
        img_out = Image.new(mode="L", size=new_size, color=(0))
        img_out.paste(img_in, (0, 0))
        draw = ImageDraw.Draw(img_out)
        draw.text((5, img_in.size[1] + 5),text,(255),font=font)
        img_out.save(path_out)

def trim_str(s, l):
    return (s[:l-3] + '...') if len(s) > l else s

# scales to a set number of bytes
def scale_image_to_size(path, path_out, max_size_b, iterations):
    if os.path.getsize(path) < max_size_b:
        shutil.copyfile(path, path_out)
    else:
        print_info("Image is too large (" + str(os.path.getsize(path)) + " bytes). Resizing...")
        img_in = Image.open(path)
        dims_jump = np.array(img_in.size)
        dims_out = np.array(img_in.size)
        last_good_size = img_in.size
        # Binary search for largest possible image dimensions
        for i in range(0, iterations):
            dims_jump = np.ceil(dims_jump/2).astype(np.int64)
            sz = 0
            with Image.open(path) as img:
                img = img.resize(dims_out, resample=Image.Resampling.NEAREST)
                img_file = BytesIO()
                img.save(img_file, 'png')
                sz = img_file.tell()
            if sz < max_size_b:
                last_good_size = dims_out
                dims_out += dims_jump
            else:
                dims_out -= dims_jump
        if max(dims_out[0], dims_out[1]) > 6144:
            sf = max(dims_out[0], dims_out[1]) / 6144.0
            last_good_size = np.round(dims_out/sf).astype(np.int64)
        if min(dims_out[0], dims_out[1]) <= 8:
            sf = min(dims_out[0], dims_out[1]) / 8.0
            last_good_size = np.round(dims_out/sf).astype(np.int64)

        with Image.open(path) as img:
                img = img.resize(last_good_size, resample=Image.Resampling.LANCZOS)
                img.save(path_out)
                print_info("Rescaled to dimensions " + str(last_good_size))
        img_in.close()

class JWSTPhoto:
    def __init__(self, product, name):
        self.product = product
        self.name = name
        self.path = ""
        self.fitsimg = None
        self.val_arr = None

        self.obs_id = product['obs_id']
        self.obj_data = obj_data[self.obs_id]

        self.proposal_id = product['proposal_id']
        self.proposal_pi = self.obj_data["proposal_pi"]
        self.obs_collection = product['obs_collection']
        self.obs_title = self.obj_data["obs_title"]
        self.filters = self.obj_data["filters"]
        self.target_name = self.obj_data["target_name"]
        self.instrument_name = self.obj_data["instrument_name"]
        self.exposure_time = self.obj_data["t_exptime"]
        self.exposure_time_formatted = strftime("%Hh:%Mm:%S", gmtime(self.exposure_time)) + ('{:.3f}'.format(self.exposure_time%1.0)).lstrip("0") + "s"
        self.obj_id = self.obj_data["objID"]
        self.s_ra = self.obj_data["s_ra"]
        self.s_dec = self.obj_data["s_dec"]
        self.start_time = Time(self.obj_data["t_min"], format='mjd').utc.iso
        self.mjd_start = self.obj_data["t_min"]
        tnm = "Target: " + self.target_name + "\n"
        if "UNKNOWN" in self.target_name.upper():
            tnm = ""
        self.label = str("Target: " + self.target_name + "\n" + 
                         "Observation Title: " + self.obs_title + "\n" +
                         "Observation (ra, dec): (" + '{:.5f}'.format(self.s_ra) + u"\N{DEGREE SIGN}, " + '{:.5f}'.format(self.s_dec) + u"\N{DEGREE SIGN})\n" +
                         "Observation Start Time: " + self.start_time + "\n" +
                         "Exposure Time: " + self.exposure_time_formatted + "\n"
                         "Instrument / Filter: " + self.instrument_name + " / " + self.filters + "\n" +
                         "Proposal I.D. / P.I.: " + str(self.proposal_id) + " / " + self.proposal_pi + "\n" +
                         "ObjID: " + str(self.obj_id))
        self.caption = str(tnm + 
                           "Observation Title: " + trim_str(self.obs_title, 80) + "\n" +
                           "Instrument: " + self.instrument_name + "\n" + 
                           "Filter: " + self.filters + "\n" +
                           "Observation Start Time: " + self.start_time + "\n" +
                           "Exposure Time: " + self.exposure_time_formatted + "\n" +
                           "ObjID: " + str(self.obj_id) + "\n" +
                           "#JWSTPhoto")
        while len(self.caption) > 280: # twitter character limit
            self.caption = self.caption.split("\n")[:-1]
    
    def calc_path(self):
        self.path = str(pathlib.Path(__file__).parent.resolve()) + "\\" + download(self.product)["Local Path"][0][2:]
        self.pngpath = self.path.split(".")[0] + ".png"
        self.pngscaledpath = self.path.split(".")[0] + "_scaled.png"
        self.pngscaledtextpath = self.path.split(".")[0] + "_scaled_text.png"

    def post(self):
        self.calc_path()
        while True:
            try:
                self.fitsimg = fits.open(self.path)
                break
            except OSError:
                print_info("File corrupted/incomplete/empty. Redownloading...")
                dl = download(self.product)
                if "error" in dl["Status"][0].lower():
                    print("ERROR DOWNLOADING .FITS FILE!!! SKIPPING!!!")
                    self.obj_id = -1
                    return None
                self.path = str(pathlib.Path(__file__).parent.resolve()) + "\\" + dl["Local Path"][0][2:]
                if os.path.exists(self.path):
                    os.remove(self.path)
                download(self.product)
                time.sleep(0.1)
        self.pngpath = self.path.split(".")[0] + ".png"
        self.pngscaledpath = self.path.split(".")[0] + "_scaled.png"
        self.pngscaledtextpath = self.path.split(".")[0] + "_scaled_text.png"
        self.val_arr = level_adjust(self.fitsimg[1].data)

        self.fitsimg.close()
        img = Image.fromarray((self.val_arr*255).astype(np.uint8))
        img = ImageOps.flip(img)
        img.save(self.pngpath)
        scale_image_to_size(self.pngpath, self.pngscaledpath, 4000000, 10)
        add_text(self.pngscaledpath, self.pngscaledtextpath, self.label)
        self.fitsimg.close()
        os.remove(self.path)
        os.remove(self.pngscaledpath)
        print_info("ZOOBER!" + self.pngscaledtextpath + " " + self.caption + " " + self.start_time)
        post_images([self.pngscaledtextpath], description=self.caption)
        shutil.copyfile(self.pngscaledtextpath, str(pathlib.Path(__file__).parent.resolve()) + "\\archive\\" + str(self.obs_id) + ".png")
        os.remove(self.pngscaledtextpath)
#============================ Main ============================#

def process_range(start_t, end_t):
    posted_images = load_set('posted_images.dat')

    past_2days = get_good_products_from(start_t, end_t)
    past_2days_fnames = get_product_filenames(past_2days)

    unposted_count = 0
    to_post = []
    for (prod, name) in zip(past_2days, past_2days_fnames):
        j = JWSTPhoto(prod, name)
        if not j.obj_id in posted_images:
            to_post.append(JWSTPhoto(prod, name))
            unposted_count += 1
    print_debug(str(unposted_count) + " unposted images found on MAST")
    print_debug("UNSORTED PHOTO ORDER:")
    for pic in to_post:
        print_debug(pic.mjd_start)
    to_post.sort(key=lambda x: x.mjd_start, reverse=False)
    print_debug("SORTED PHOTO ORDER:")
    for pic in to_post:
        print_debug(pic.mjd_start)
    print_info("downloading unposted image files...")
    for pic in to_post:
        pic.post()
        posted_images.add(pic.obj_id)
        save_set(posted_images, "posted_images.dat")

ctime = Time.now().mjd
ctime = 59940.0
# process_range(ctime - 1000.0, ctime)
for i in range(250, -1, -1):
    process_range(ctime - i*1.0 - 1.1, ctime - i*1.0)
    print("RANG " + str(i))

#while True:
#    time.sleep(60*20)
#    ctime = Time.now().mjd
#    process_range(ctime - 0.5, ctime)
