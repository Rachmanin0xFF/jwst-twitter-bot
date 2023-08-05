# JWST Photo Bot
# @author Adam Lastowka

#============================ Imports ============================#

# Core / IO
import os
import pathlib
import configparser
import pickle
from time import strftime
from time import gmtime
import time

# Scipy stack
import numpy as np

# AstroPy
from astropy.io import fits
from astroquery.mast import Observations
import astroquery.exceptions
from astropy.time import Time
from astropy.io import fits
from astropy.table import vstack, Table

#============================ Logging & Presistent Memory ============================#
#logging.basicConfig(filename='log.txt', encoding='utf-8', level=logging.DEBUG)
def log_print(s):
    with open("log.txt", "a") as f:
        f.write(s + "\n")
ctime = Time.now()
log_print("Run at " + str(ctime))
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

# Config

config = configparser.ConfigParser()
config.read(str(pathlib.Path(__file__).parent.resolve()) + '/config.ini')
# Don't post images with titles exactly matching any of these
INSTRUMENTS_TO_QUERY = config["queries"]["INSTRUMENTS_TO_QUERY"].split(",")
IGNORE_TITLES = config["queries"]["IGNORE_TITLES_MATCHING"].split(",")
IGNORE_TITLES_CONTAINING = config["queries"]["IGNORE_TITLES_CONTAINING"].split(",")
ALWAYS_INCLUDE_TITLES_CONTAINING = config["queries"]["ALWAYS_INCLUDE_TITLES_CONTAINING"].split(",")
ALWAYS_INCLUDE_TARGETS_CONTAINING = config["queries"]["ALWAYS_INCLUDE_TARGETS_CONTAINING"].split(",")
BYPASS_FILTER = (config["queries"]["BYPASS_FILTER"].lower()=="true")

lookback_amount=int(config["queries"]["days_to_look_back"])
lookback_stepsize=int(config["queries"]["mast_query_length_in_days"])

#============================ MAST Download ============================#

# MAST data comes in bundles called "observations".
# This *global* dictionary contains all observation data downloaded during the bot's most recent run.
# The keys are obs_ids.
obs_data = {}

ctime = Time.now()
def get_JWST_products_from(start_time, end_time):
    """
    Gets calib=3 level public NIRCAM and MIRI products within a given time range.
    Also pushes any downloaded observations onto the obs_data dictionary.
    Parameters:
        start_time: A number representing the MJD (Modified Julian Date) start time of the range
        end_time: MJD end of time range
    Returns:
        An AstroPy Table containing a list of I2D products.
    """
    # Observations.query_criteria() output columns:
    # ['dataproduct_type', 'calib_level', 'obs_collection', 'obs_id', 'target_name', 
    #  's_ra', 's_dec', 't_min', 't_max', 't_exptime', 'wavelength_region', 'filters', 
    #  'em_min', 'em_max', 'target_classification', 'obs_title', 't_obs_release', 
    #  'instrument_name', 'proposal_pi', 'proposal_id', 'proposal_type', 'project', 
    #  'sequence_number', 'provenance_name', 's_region', 'jpegURL', 'dataURL', 
    #  'dataRights', 'mtFlag', 'srcDen', 'intentType', 'obsid', 'objID']

    # Output table columns:
    # ['obsID', 'obs_collection', 'dataproduct_type', 'obs_id', 'description', 'type', 'dataURI', 'productType',
    #  'productGroupDescription', 'productSubGroupDescription', 'productDocumentationURL', 'project',
    #  'prvversion', 'proposal_id', 'productFilename', 'size', 'parent_obsid', 'dataRights', 'calib_level']
    print("Querying MAST from " + str(start_time) + " to " + str(end_time))
    log_print("Q " + str(start_time) + " " + str(end_time))
    obsByName = Observations.query_criteria(obs_collection="JWST",
                                            instrument_name=INSTRUMENTS_TO_QUERY,
                                            t_min=[start_time, end_time],
                                            calib_level=3,
                                            dataproduct_type="image")
    all_result_count = len(obsByName)
    print(obsByName.colnames)
    obsByName = obsByName[(obsByName["dataRights"]=="PUBLIC")]
    print("Number of public results from JWST NIRCAM/MIRI: " + str(len(obsByName)))
    print("Number of exclusive/restricted results: " + str(all_result_count-len(obsByName)))
    print(obsByName[:4])

    for o in obsByName:
        obs_data[o["obs_id"]] = o
    alli2d = []
    k = 0
    for o in obsByName:
        k += 1
        print("Opening object " + str(k) + "/" + str(len(obsByName)))
        try:
            data_products = None
            while data_products is None:
                try:
                    data_products = Observations.get_product_list(o)
                except OSError:
                    data_products = None

            calibrated = data_products[(data_products['calib_level'] >= 3)]
            print("Total calib_level=3 products in objects:" + str(len(calibrated)))
            i2d = calibrated[(calibrated["productSubGroupDescription"] == "I2D")]
            print("Total calib_level=3 && I2D products in result:" + str(len(i2d)))
            alli2d.append(i2d)
        except astroquery.exceptions.InvalidQueryError:
            print("Invalid query!")
            pass
    if len(alli2d)==0:
        return Table({})
    else:
        return vstack(alli2d)

def download(products):
    '''Uses AstroPy's download_products() to download a given list of I2D products.'''
    keko = None
    while True:
        try: 
            keko = Observations.download_products(products, mrp_only=True)
            break
        except OSError:
            print('SSL CONNECTION INTERRUPTED')
    return keko

def get_product_filenames(products):
    return [x["productFilename"] for x in products]

#============================ JWSTPhoto Class ============================#

def trim_str(s, l):
    return (s[:l-3] + '...') if len(s) > l else s

# This class contains a single I2D product (photo).
class JWSTPhoto:
    def __init__(self, product, name):
        self.product = product
        self.name = name
        self.path = ""
        self.fitsimg = None
        self.val_arr = None

        self.obs_id = product['obs_id']
        self.obs_data = obs_data[self.obs_id]

        self.proposal_id = product['proposal_id']
        self.proposal_pi = self.obs_data["proposal_pi"]
        self.obs_collection = product['obs_collection']
        self.obs_title = self.obs_data["obs_title"]
        self.filters = self.obs_data["filters"]
        self.target_name = self.obs_data["target_name"]
        self.instrument_name = self.obs_data["instrument_name"]

        # exposure time
        self.exposure_time = self.obs_data["t_exptime"]
        self.exposure_time_formatted = strftime("%Hh:%Mm:%S", gmtime(self.exposure_time)) + ('{:.3f}'.format(self.exposure_time%1.0)).lstrip("0") + "s"
        
        # the OBJID
        self.obj_id = self.obs_data["objID"]

        # coordinates
        self.s_ra = self.obs_data["s_ra"]
        self.s_dec = self.obs_data["s_dec"]

        self.start_time = Time(self.obs_data["t_min"], format='mjd').utc.iso # 
        self.mjd_start = self.obs_data["t_min"]

        # temporary target name variable
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
            self.caption = (self.caption.split("\n")[:-1]).join("\n")
    
    def download(self):
        self.path = str(pathlib.Path(__file__).parent.resolve()) + "/" + download(self.product)["Local Path"][0][2:]
    
    def is_interesting(self):
        if BYPASS_FILTER:
            return True
        interesting = True
        if (self.obs_title).lower() in [x.lower for x in IGNORE_TITLES]:
            interesting = False
        if any(x.lower() in (self.obs_title).lower() for x in IGNORE_TITLES_CONTAINING):
            interesting = False
        if any(x.lower() in (self.obs_title).lower() for x in ALWAYS_INCLUDE_TITLES_CONTAINING):
            interesting = True
        if any(x.lower() in (self.target_name).lower() for x in ALWAYS_INCLUDE_TARGETS_CONTAINING):
            interesting = True
        return interesting

    def load(self):
        '''Loads (and downscales, if necessary) the photo's .fits file into memory.'''
        try:
            self.download()
        except ValueError:
            pass
        while True:
            try:
                self.fitsimg = fits.open(self.path)
                break
            except (OSError, ValueError):
                os.remove(self.path)
                self.download()
        self.val_arr = np.copy(self.fitsimg[1].data)
        self.fitsimg.close()
        os.remove(self.path)
        self.pre_downscale()

    def pre_downscale(self):
        # Direct nearest-filtered downsampling of numpy float64 data.
        # This only happens to VERY large images, so artefacts don't really matter.
        # I use arbitrary cutoff based on the amount of RAM I have available -- a (2^13)x(2^13) float64 array is about 0.5GB.
        MAX_PIXELS = 8192**2
        while len(self.val_arr)*len(self.val_arr[0]) > MAX_PIXELS:
            print("Raw image " + str(self.obj_id) + " too large! Downscaling x0.5...")
            self.val_arr = (self.val_arr[::2,::2])
    
    def save(self):
        '''Saves the photo's numpy and description data to data_queue.'''
        ctime = Time.now().mjd
        self.numpypath = "./data_queue/" + self.path.split(".")[0].split("\\")[-1] + "-" + str(ctime) + ".npy"
        self.infopath = "./data_queue/" + self.path.split(".")[0].split("\\")[-1] + "-" + str(ctime) + ".txt"
        print("Saving obj_id=" + str(self.obj_id) + " to " + self.numpypath)
        np.save(self.numpypath, self.val_arr)
        with open(self.infopath, 'w') as f:
            f.write("~LABEL\n")
            f.write(self.label)
            f.write("\n~CAPTION\n")
            f.write(self.caption)

#============================ Photo Sorting and Saving ============================#

def search_time_range(start_t, end_t):
    downloaded_images = load_set('downloaded_images.dat')

    # Get products and filenames
    in_range = get_JWST_products_from(start_t, end_t)
    in_range_fnames = get_product_filenames(in_range)
    print(in_range)

    # Put products into an array and sort
    to_process = []
    for (prod, name) in zip(in_range, in_range_fnames):
        j = JWSTPhoto(prod, name)
        if not j.obj_id in downloaded_images:
            to_process.append(j)
    print(str(len(to_process)) + " unprocessed images found on MAST")
    to_process.sort(key=lambda x: x.mjd_start, reverse=False)

    print("downloading unposted image files...")
    for pic in to_process:
        if pic.is_interesting() or True:
            pic.load() # This function also downscales if necessary
            pic.save()
        if not pic in downloaded_images:
            log_print(str(pic.obs_id) + " " + str(pic.obj_id) + " " + str(pic.is_interesting()))
            downloaded_images.add(pic.obj_id)
            save_set(downloaded_images, "downloaded_images.dat")

if __name__ == "__main__":
    if not os.path.exists("./data_queue"):
        os.makedirs("./data_queue")
    while True:
        ctime = Time.now().mjd
        # Loop forwards through time beginning 100d back
        for i in range(lookback_amount, -1, -lookback_stepsize):
            search_time_range(ctime - (i + 1.05)*lookback_stepsize, ctime - i*lookback_stepsize)
            time.sleep(2.0)
        time.sleep(30.0*60.0)