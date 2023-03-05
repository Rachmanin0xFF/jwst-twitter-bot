
# Twitter
import tweepy

# Core / IO
import pathlib
import configparser
import time
import shutil
import os
from io import BytesIO
import time
import pickle

# Image processing (PIL)
import PIL
from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw 
from PIL import ImageOps
PIL.Image.MAX_IMAGE_PIXELS = None

# Scipy stack
import numpy as np
import scipy.stats

#============================ I/O ============================#

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

# The config.ini file contains all the bot's keys -- it's not on Github, of course.
config = configparser.ConfigParser()
config.read(str(pathlib.Path(__file__).parent.resolve()) + '/config.ini')

consumer_key = config['twitter']['consumer_key']
consumer_key_secret = config['twitter']['consumer_key_secret']

access_token = config['twitter']['access_token']
access_token_secret = config['twitter']['access_token_secret']

def post_images_dummy(paths, description="No description provided."):
    # For debugging purposes
    print("Description:\n---------------")
    print(description)
    print("-----------------------------")

def post_images(paths, text="No description provided."):
    """
    Posts a set of images to twitter with a given description.
    Parameters:
        paths (list of strings): paths to the images to post
        text: The description to post the image with (must be <280 characters)
    """
    print("Posting Photo...")
    # Authorize and connect with keys
    # I do this every time, the auth eventually times out otherwise.
    auth=tweepy.OAuthHandler(consumer_key,consumer_key_secret)
    auth.set_access_token(access_token,access_token_secret)
    api=tweepy.API(auth, wait_on_rate_limit=True, retry_count=10) # USE TWEEPY'S RATE LIMIT!
    media_ids = []
    for p in paths:
        print("Photo path: " + p)
        res = api.media_upload(p)
        media_ids.append(res.media_id)
        if len(media_ids) == 4:
            break
    status = api.update_status(status=text, media_ids=media_ids)
    print("Posted status, output follows:")
    print(str(status))
    time.sleep(60) # WAIT FORTY SECONDS TO ENSURE WE DON'T EXCEED TWITTER'S 300 POST / 3HRS MAXIMUM
                   # This code is (and will remain) single-threaded, so I don't have to worry about overlapping calls.

#============================ Image Processing ============================#

def to1(x):
    '''Sigmoid function that maps (-inf,inf) to (0,1). Centered at x=1 (that is, to1(1)=0.5).'''
    return 0.5+(2.0*x-2.0)/(2*np.sqrt((2.0*x-2.0)*(2.0*x-2.0)+1.0))

def trim_ends(data, cutoff):
    '''Trims end quantiles given by cutoff.'''
    cth = np.quantile(data, cutoff)
    ctl = np.quantile(data, 1.0-cutoff)
    f1 = data[data < cth]
    return f1[f1 > ctl]

def expand_highs(x):
    '''A piecewise function to expand contrast in values between 0.9 and 1'''
    return np.piecewise(x, [x <= 0.9, x > 0.9], [lambda x: x*0.8/0.9, lambda x: 100.0/9.0*(x-0.9)**2 + 0.8*x/0.9])

def image_histogram_equalization(image, number_bins=10000):
    # from http://www.janeriksolem.net/histogram-equalization-with-python-and.html

    # get image histogram
    r = image.flatten()
    r = r[~np.isnan(r)]
    r = r[np.isfinite(r)]
    try:
        image_histogram, bins = np.histogram(image.flatten(), number_bins, density=True)
    except ValueError:
        return -1
    cdf = image_histogram.cumsum() # cumulative distribution function
    cdf = cdf / cdf[-1] # normalize

    # use linear interpolation of cdf to find new pixel values
    image_equalized = np.interp(image.flatten(), bins[:-1], cdf)

    return image_equalized.reshape(image.shape)

def level_adjust(fits_arr):
    """
    Tone-maps a .fits image from the JWST using a robust combination of techniques.
    Parameters:
        fits_arr: a 2D numpy float64 array obtained from a .fits file.
    """
    hist_dat = fits_arr.flatten()
    # Don't consider zero or infinite values when histogramming
    hist_dat = hist_dat[np.isfinite(hist_dat)]
    hist_dat = hist_dat[np.nonzero(hist_dat)]
    if len(hist_dat) == 0:
        return -1
    zeros = np.abs(np.sign(fits_arr))
    minval = np.quantile(hist_dat, 0.03)
    maxval = np.quantile(hist_dat, 0.98)
    rescaled = (fits_arr-minval)/(maxval-minval)
    rescaled_no_outliers = np.maximum(rescaled, np.quantile(rescaled, 0.002))
    rescaled_no_outliers = np.minimum(rescaled_no_outliers, np.quantile(rescaled_no_outliers, 1.0-0.002))
    img_eqd = image_histogram_equalization(rescaled_no_outliers)
    if isinstance(img_eqd, int):
        return -1
    img_eqd = (pow(img_eqd, 4.0) + pow(img_eqd, 8.0) + pow(img_eqd, 16.0))/3.0
    adjusted = expand_highs((img_eqd + to1(rescaled))*0.5)
    return np.clip(adjusted*zeros, 0.0, 1.0)

font = ImageFont.truetype("PTMono-Regular.ttf", 14)
def add_text(path_in, path_out, text):
    """
    Adds text to an image.
    Parameters:
        path_in: Input image path
        path_out: Output photo path
        text: A string containing the text to add
    """
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

# scales to a set number of bytes
def scale_image_to_size(path, path_out, max_size_b, iterations):
    if os.path.getsize(path) < max_size_b:
        with Image.open(path) as img_in:
            dims_out = np.array(img_in.size)

            # .PNG compression means that a very homogeneous, non-noisy photo can have a small file size
            # while still being absolutely huge (in terms of its dimensions).
            # 
            # I don't want this bot posting images with too many pixels, because Twitter doesn't like it.
            # So I set the cap at 3840x2160=8294400 pixels (4K resolution).

            if dims_out[0]*dims_out[1] > 8294400:
                sf = dims_out[0]*dims_out[1]/8294400.0
                last_good_size = np.round(dims_out/sf).astype(np.int64)
                print("Over ~8m pixels, shrinking...")
                with Image.open(path) as img:
                        img = img.resize(last_good_size, resample=Image.Resampling.LANCZOS)
                        img.save(path_out)
                        print("Rescaled to dimensions " + str(last_good_size))
                        return last_good_size
        shutil.copyfile(path, path_out)
        with Image.open(path) as img_in:
            return img_in.size
    
    else:
        print("Image file size is too large (" + str(os.path.getsize(path)) + " bytes). Resizing...")
        with Image.open(path) as img_in:
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
            
            # Not sure why I chose 6144, there's probably a reason.
            if max(dims_out[0], dims_out[1]) > 6144:
                sf = max(dims_out[0], dims_out[1]) / 6144.0
                last_good_size = np.round(dims_out/sf).astype(np.int64)
            
            # We need to do the 4K check here, too
            if dims_out[0]*dims_out[1] > 8000000:
                sf = dims_out[0]*dims_out[1]/8000000.0
                last_good_size = np.round(dims_out/sf).astype(np.int64)
                print("Over ~8m pixels, shrinking...")
            
            # <8 pixels is too small! Upscale it to 8 pixels if this happens.
            # (still too small, but not invisible, at least)
            if min(dims_out[0], dims_out[1]) <= 8:
                sf = min(dims_out[0], dims_out[1]) / 8.0
                last_good_size = np.round(dims_out/sf).astype(np.int64)
            
            print("Total pixels:", dims_out[0]*dims_out[1])

            with Image.open(path) as img:
                    img = img.resize(last_good_size, resample=Image.Resampling.LANCZOS)
                    img.save(path_out)
                    print("Rescaled to dimensions " + str(last_good_size))
                    return last_good_size

#============================ Main ============================#

def to_photo_BW(description, data, path, objid):
    img_path = path + ".png"
    scaled_img_path = path + "_scaled.png"
    scaled_text_img_path = path + "_scaled_text.png"
    arr = level_adjust(data)
    img = Image.fromarray((arr*255).astype(np.uint8))
    img = ImageOps.flip(img)
    img.save(img_path, format="PNG")
    scale_image_to_size(img_path, scaled_img_path, 3500000, 10)
    add_text(scaled_img_path, scaled_text_img_path, description)
    os.remove(img_path)
    os.remove(scaled_img_path)
    return scaled_text_img_path

if __name__ == "__main__":
    posted_images = load_set('posted_images.dat')
    while True:
        metadata = list(filter(lambda s : ".txt" in s, os.listdir('./data_queue')))
        time.sleep(10) # Give the processor time to finish saving if we caught it in the middle of doing so
        for txt_path in metadata:
            print("Found new photo at " + txt_path + "!\nPosting...")
            with open("./data_queue/" + txt_path, 'r') as f:
                sections = f.read().split("~")
                description = '\n'.join(sections[1].split("\n")[1:-1])
                caption = '\n'.join(sections[2].split("\n")[1:])
                obj_id = int(caption.split("\n")[-2].split(" ")[1])
                data_path = "./data_queue/" + ".".join(txt_path.split(".")[0:2]) + ".npy"
                data = np.load(data_path)
                
                if not obj_id in posted_images:
                    output_path = to_photo_BW(description, data, "./data_queue/" + ".".join(txt_path.split(".")[0:2]), obj_id)
                    post_images([output_path], text=caption)
                
                    # Remember that we posted this
                    posted_images.add(obj_id)
                    save_set(posted_images, "posted_images.dat")

                archive_path = "./archive/" + ".".join(txt_path.split(".")[0:2]) + ".png"
                shutil.copy(output_path, archive_path)
                os.remove(output_path)
                os.remove(data_path)

            os.remove("./data_queue/" + txt_path)