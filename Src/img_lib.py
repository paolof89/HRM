import os
import yaml
import pandas as pd
from img_utils import get_cell_idx
import gdal
import numpy as np

with open('../public_config.yml', 'r') as cfgfile:
    public_config = yaml.load(cfgfile)

with open('../private_config.yml', 'r') as cfgfile:
    tokens = yaml.load(cfgfile)


class RasterGrid:
    """
    Class
    -----
    Handles the raster grid, and related functionalities like downloading the relevant satellite images
    from Google Static API.
    """

    def __init__(self,raster=os.path.join("../Data","Satellite",public_config["satellite"]["grid"]),image_dir=os.path.join("../Data","Satellite",public_config["satellite"]["source"])):

        self.x_size, \
        self.top_left_x_coords, \
        self.top_left_y_coords, \
        self.centroid_x_coords, \
        self.centroid_y_coords, \
        self.bands_data = self.__read_raster(raster)
        self.url = None
        self.output_image_dir=image_dir
        self.config = public_config

    def get_gridcoordinates(self, file=os.path.join("../Data","Datasets",public_config["dataset"]["filename"])):

        dataset= pd.read_csv(file)
        list_i=[]
        list_j=[]
        for index, row in dataset.iterrows():
            i,j = get_cell_idx(row['gpsLongitude'],row['gpsLatitude'], self.top_left_x_coords, self.top_left_y_coords)
            list_i.append(i)
            list_j.append(j)
        return (list_i,list_j)

    def get_gpscoordinates(self, list_i, list_j, step=public_config["satellite"]["step"]):
        """
        given a set of i and j it returns the lists on longitude and latitude.
        :param list_i: list of i (raster/grid references)
        :param list_j: list of j (raster/grid references)
        :param step: the steps around the cluster
        :return: two lists containing the gps coordinates corresponding to i and j.
        """

        lon = []
        lat = []
        # for all i and j
        for i, j in zip(list_i, list_j):
            # for all steps
            # for a in range(-step, 1+step):
            #     for b in range(-step, 1+step):
            #         lon.append(self.centroid_x_coords[i + a])
            #         lat.append(self.centroid_y_coords[j + b])
            lon.append(self.centroid_x_coords[i])
            lat.append(self.centroid_y_coords[j])

        return(lon, lat)

    def __read_raster(self, raster_file):
        """
        Function
        --------
        read_raster

        Given a raster file, get the pixel size, pixel location, and pixel value

        Parameters
        ----------
        raster_file : string
            Path to the raster file

        Returns
        -------
        x_size : float
            Pixel size
        top_left_x_coords : numpy.ndarray  shape: (number of columns,)
            Longitude of the top-left point in each pixel
        top_left_y_coords : numpy.ndarray  shape: (number of rows,)
            Latitude of the top-left point in each pixel
        centroid_x_coords : numpy.ndarray  shape: (number of columns,)
            Longitude of the centroid in each pixel
        centroid_y_coords : numpy.ndarray  shape: (number of rows,)
            Latitude of the centroid in each pixel
        bands_data : numpy.ndarray  shape: (number of rows, number of columns, 1)
            Pixel value
        """

        gdal.UseExceptions()

        raster_dataset = gdal.Open(raster_file, gdal.GA_ReadOnly)
        # get project coordination
        bands_data = []
        # Loop through all raster bands
        for b in range(1, raster_dataset.RasterCount + 1):
            band = raster_dataset.GetRasterBand(b)
            bands_data.append(band.ReadAsArray())
            no_data_value = band.GetNoDataValue()
        bands_data = np.dstack(bands_data)

        # Get the metadata of the raster
        geo_transform = raster_dataset.GetGeoTransform()
        (upper_left_x, x_size, x_rotation, upper_left_y, y_rotation, y_size) = geo_transform

        # Get location of each pixel
        x_size = 1.0 / int(round(1 / float(x_size)))
        y_size = - x_size
        y_index = np.arange(bands_data.shape[0])
        x_index = np.arange(bands_data.shape[1])
        top_left_x_coords = upper_left_x + x_index * x_size
        top_left_y_coords = upper_left_y + y_index * y_size
        # Add half of the cell size to get the centroid of the cell
        centroid_x_coords = top_left_x_coords + (x_size / 2)
        centroid_y_coords = top_left_y_coords + (y_size / 2)

        return x_size, top_left_x_coords, top_left_y_coords, centroid_x_coords, centroid_y_coords, bands_data

    def download_images(self, list_i, list_j,step = public_config["satellite"]["step"],provider=public_config["satellite"]["source"]):
        """
        Function
        --------
        given the list of tiles, it downloads the corresponding satellite images.

        Parameters
        ----------
        list_i, list_j: the list of tiles that need an image.

        """
        from joblib import Parallel, delayed
        import multiprocessing

        cnt=0
        for i, j in zip(list_i, list_j):
            cnt+=1

            if cnt%10 == 0:
                print("{} images downloaded".format(cnt))

            file_path = self.output_image_dir + '/' + str(i) + '_' + str(j) + '/'
            if not os.path.isdir(file_path):
                os.makedirs(file_path)

            for a in range(-step, 1+step):

                # parallelize on the images per tile (inputs)
                inputs = range(-step, 1+step)

                # find available cores
                num_cores = multiprocessing.cpu_count()

                # run parallel job
                Parallel(n_jobs=num_cores)(delayed(self.img_multiproc_wrapper)(i, j, a, b, provider, file_path)
                                           for b in inputs)

    def img_multiproc_wrapper(self, i, j, a, b, provider, file_path):
        # wrapper for the url creation (depending on the engine) and for the pulling and saving of the image.
        lon = self.centroid_x_coords[i + a]
        lat = self.centroid_y_coords[j + b]

        self.url = self.__produce_url(lon, lat, provider)

        file_name = str(i + a) + '_' + str(j + b) + '.jpg'

        self.__save_img(file_path, file_name)

    def __produce_url(self, lon, lat, provider):
        # wrapper for the creation of the url depending on the engine.
        if provider == 'Google':
            return('https://maps.googleapis.com/maps/api/staticmap?center=' + str(lat) + ',' +
                    str(lon) + '&zoom=16&size=400x500&maptype=satellite&key=' + tokens['Google'])

        elif provider == 'Bing':
            imagery_set = "Aerial"
            zoom_level = "16"
            map_size = "400,500"
            center_point = str(lat) + "," + str(lon)

            return("http://dev.virtualearth.net/REST/v1/Imagery/Map/" + imagery_set + "/" + center_point +
                    "/" + zoom_level + "?mapSize=" + map_size + "&key=" + tokens['Bing'])
        else:
            print("ERROR: Wrong API {}".format(provider))

    def __save_img(self, file_path, file_name):
        """
        Function
        --------
        this private method is used by the "download_images" to call the Google API
        for every pair of coordinates, to parse the request and to save the image to the folder.
        """
        import numpy as np
        import urllib.request
        import urllib.error
        from scipy import misc
        from scipy.misc.pilutil import imread
        from io import BytesIO

        # try to pull the image

        if os.path.exists(file_path + file_name):
            print("{}{} already downloaded".format(file_path,file_name))

        else:
            try:
                ur = urllib.request.urlopen(self.url).read()
                buffer = BytesIO(ur)

                image = imread(buffer, mode='RGB')

                ## Do not download images in places where Google or Bing does not have any image

                #if np.array_equal(image[:, :10, :], image[:, 10:20, :]):
                    #print("bad image")
                #else:

                misc.imsave(file_path + file_name, image[50:450, :, :])

            except urllib.error.HTTPError as err:

                # try a second time!!!
                try:
                    print('second try for url {}'.format(self.url))
                    ur = urllib.request.urlopen(self.url).read()
                    buffer = BytesIO(ur)

                    image = imread(buffer, mode='RGB')

                    ## Do not download images in places where Google or Bing does not have any image

                    #if np.array_equal(image[:, :10, :], image[:, 10:20, :]):
                        #print("bad image")
                    #else:

                    misc.imsave(file_path + file_name, image[50:450, :, :])

                except urllib.error.HTTPError as err:

                    print('error code: \n', err.code)
                    print('error message: \n', err.read())
                    import sys
                    sys.exit("Error message")

    def get_coordinates_of_country(self, country):
        """
        given the name of a country (or a list of countries), it returns all the coordinates within that country.
        Based on geocoder library.
        :return:
        """
        import geocoder

        list_lat = []
        list_lon = []

        for lat in range(-35, 60, 1):
            if lat % 10 == 0: print('INFO: getting latitudes ', lat)

            for lon in range(-120, 150, 1):
                g = geocoder.osm([lat, lon], method='reverse')
                try:
                    if g.country == country:
                        list_lat.append(lat)
                        list_lon.append(lon)
                except TypeError:
                    pass
        return list_lat, list_lon

