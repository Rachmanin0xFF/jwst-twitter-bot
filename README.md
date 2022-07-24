![samele photo](banner.png)

# JWST Photo Bot

Hi! I am the [JWST Photo Bot](https://twitter.com/JWSTPhotoBot)! I automatically process and post images from the James Webb Space Telescope to Twitter!

## Basic Q & A

### Q: What is the JWST?
A: The James Webb Space Telescope (JWST) is a space telescope that was launched from the Earth in December 2022. It rests at a stable point (the earth-sun L2) in space 5 times further away from Earth than the Moon.

### Q: Why are the photos in black and white?
A: While most publicized images from the JWST are in full color, these photos are always combinations of three or more seperate black and white photos taken with different instruments (cameras) and filters. Right now this bot doesn't try to combine the black and white images into color ones (though it might in the future).

### Q: Why does the bot post multiple copies of the same photo?
A: Look carefully -- the photos are probably not the same! JWST takes photos in different wavelengths of light. Some subjects can look very similar, even across different wavelengths.

### Q: These photos look bad / noisy / overexposed!
A: Typically, when you see images from JWST, Hubble, or any other space telescope, they have been carefully edited and fine-tuned **by hand**. JWST does not provide data in a format that can be immediately displayed on a computer monitor, and squishing it down to a computer screen without losing detail is a nontrivial task. The solution I use here is usually decent, but it has some flaws.

### Q: What are NIRCAM and MIRI?
A: Think of them as the JWST's different cameras. NIRCAM (Near InfraRed CAMera) captures wavelengths of light between 0.6 and 5 μm (micrometers), while MIRI (Mid InfraRed Instrument) captures longer wavelengths of light between 4.9 and 28.8 μm. The JWST has two other instruments (NIRISS and NIRSpec), but these are designed for spectroscopy, so photos made with their data are more confusing and less appealing to the public.

## Technical Information

### MAST Database
This bot gets its data from the [MAST Portal](https://mast.stsci.edu/portal/Mashup/Clients/Mast/Portal.html) (Barbara A. Mikulski Archive for Space Telescopes). Specifically, it asks for stage-3 calibrated public data from JWST's MIRI and NIRCAM instruments (I2D .fits files). It tries to post its photos in chronological order of time captured, but MAST isn't always updated chronologically, so out-of-order images will still appear sometimes. However, this bot will not post images that are more than a month (30 days) old.

### Image Processing
I use a two-pronged approach here.

First, I compute the .fits array's histograms and clip the top 0.2% and bottom 0.98% of the values. I histogram-equalize the resulting array (10,000 bins) and transform it by `f(x) = (x^4 + x^8 + x^16) / 3.0`. This essentially matches the photo's histogram to the ideal "space photo" histogram -- mostly dark, with some bright spots, and some REALLY bright spots. However, the equalization can sometimes introduce additional noise, and the power transformation can hide interesting darker parts of the image (like large gas clouds).

Second, I take the .fits array's histogram and rescale the data's (3rd percentile, 98th percentile) to the (0.0, 1.0) range. Then I apply a sigmoid that remaps the outliers to (0, 1): `f(x) = 0.5 + (2x - 2) / (2*sqrt((2x - 2)^2 + 1.0))`. This provides a nice pseudo-linear remapping that still (technically) captures the full range of the data. I don't bother gamma-correcting the levels because the sigmoid sort of handles that.

I average these two values to get the final photo. Both of these functions are monotonic and remap the full value range to (0.0, 1.0). Realistically, a ton of this detail is lost when the floating-point values are converted to bytes in the .png, but most of the data is recoverable before this point.
