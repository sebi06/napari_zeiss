# -*- coding: utf-8 -*-

#################################################################
# File        : md_tools.py
# Version     : 0.0.1
# Author      : czsrh
# Date        : 18.11.2020
# Institution : Carl Zeiss Microscopy GmbH
#
# Copyright (c) 2020 Carl Zeiss AG, Germany. All Rights Reserved.
#################################################################


import czifile as zis
from apeer_ometiff_library import omexmlClass
import os
from pathlib import Path
import xmltodict
import numpy as np
from collections import Counter
from lxml import etree as ET
from aicsimageio import AICSImage, imread, imread_dask
from aicspylibczi import CziFile
import dask.array as da
import pandas as pd
import tifffile
import pydash

try:
    import napari
except ModuleNotFoundError as error:
    print(error.__class__.__name__ + ": " + error.msg)

from PyQt5.QtWidgets import (
    QHBoxLayout,
    QFileDialog,
    QDialogButtonBox,
    QWidget,
    QTableWidget,
    QTableWidgetItem,
)
from PyQt5.QtCore import Qt
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import QFont


def get_imgtype(imagefile):
    """Returns the type of the image based on the file extension - no magic

    :param imagefile: filename of the image
    :type imagefile: str
    :return: string specifying the image type
    :rtype: str
    """

    imgtype = None

    if imagefile.lower().endswith('.ome.tiff') or imagefile.lower().endswith('.ome.tif'):
        # it is on OME-TIFF based on the file extension ... :-)
        imgtype = 'ometiff'

    elif imagefile.lower().endswith('.tiff') or imagefile.lower().endswith('.tif'):
        # it is on OME-TIFF based on the file extension ... :-)
        imgtype = 'tiff'

    elif imagefile.lower().endswith('.czi'):
        # it is on CZI based on the file extension ... :-)
        imgtype = 'czi'

    elif imagefile.lower().endswith('.png'):
        # it is on CZI based on the file extension ... :-)
        imgtype = 'png'

    elif imagefile.lower().endswith('.jpg') or imagefile.lower().endswith('.jpeg'):
        # it is on OME-TIFF based on the file extension ... :-)
        imgtype = 'jpg'

    return imgtype


def create_metadata_dict():
    """A Python dictionary will be created to hold the relevant metadata.

    :return: dictionary with keys for the relevant metadata
    :rtype: dict
    """

    metadata = {'Directory': None,
                'Filename': None,
                'Extension': None,
                'ImageType': None,
                'AcqDate': None,
                'TotalSeries': None,
                'SizeX': None,
                'SizeY': None,
                'SizeZ': 1,
                'SizeC': 1,
                'SizeT': 1,
                'SizeS': 1,
                'SizeB': 1,
                'SizeM': 1,
                'Sizes BF': None,
                'DimOrder BF': None,
                'DimOrder BF Array': None,
                'Axes_czifile': None,
                'Shape_czifile': None,
                'czi_isRGB': None,
                'czi_isMosaic': None,
                'ObjNA': None,
                'ObjMag': None,
                'ObjID': None,
                'ObjName': None,
                'ObjImmersion': None,
                'XScale': None,
                'YScale': None,
                'ZScale': None,
                'XScaleUnit': None,
                'YScaleUnit': None,
                'ZScaleUnit': None,
                'DetectorModel': [],
                'DetectorName': [],
                'DetectorID': [],
                'DetectorType': [],
                'InstrumentID': [],
                'Channels': [],
                'ChannelNames': [],
                'ChannelColors': [],
                'ImageIDs': [],
                'NumPy.dtype': None
                }

    return metadata


def get_metadata(imagefile,
                 omeseries=0,
                 round_values=False):
    """Returns a dictionary with metadata depending on the image type.
    Only CZI and OME-TIFF are currently supported.

    :param imagefile: filename of the image
    :type imagefile: str
    :param omeseries: series of OME-TIFF file, , defaults to 0
    :type omeseries: int, optional
    :param round_values: option to round some values, defaults to TrueFalse
    :type round_values: bool, optional
    :return: metadata - dict with the metainformation
    :rtype: dict
    :return: additional_mdczi - dict with additional the metainformation for CZI only
    :rtype: dict
    """

    # get the image type
    imgtype = get_imgtype(imagefile)
    print('Detected Image Type (based on extension): ', imgtype)

    md = {}
    additional_md = {}

    if imgtype == 'ometiff':

        # parse the OME-XML and return the metadata dictionary and additional info
        md = get_metadata_ometiff(imagefile, series=omeseries)

    elif imgtype == 'czi':

        # parse the CZI metadata return the metadata dictionary and additional info
        md = get_metadata_czi(imagefile, dim2none=False)
        additional_md = get_additional_metadata_czi(imagefile)

    # TODO - Remove this when issue is fixed
    if round_values:
        # temporary workaround for slider / floating point issue in Napari viewer
        # https://forum.image.sc/t/problem-with-dimension-slider-when-adding-array-as-new-layer-for-ome-tiff/39092/2?u=sebi06

        md['XScale'] = np.round(md['XScale'], 3)
        md['YScale'] = np.round(md['YScale'], 3)
        md['ZScale'] = np.round(md['ZScale'], 3)
    else:
        # no metadate will be returned
        print('Scales will not be rounded.')

    return md, additional_md


def get_metadata_ometiff(filename, series=0):
    """Returns a dictionary with OME-TIFF metadata.

    :param filename: filename of the OME-TIFF image
    :type filename: str
    :param series: Image Series, defaults to 0
    :type series: int, optional
    :return: dictionary with the relevant OME-TIFF metainformation
    :rtype: dict
    """

    with tifffile.TiffFile(filename) as tif:
        try:
            # get OME-XML metadata as string the old way
            omexml_string = tif[0].image_description.decode('utf-8')
        except TypeError as e:
            print(e)
            omexml_string = tif.ome_metadata

    # get the OME-XML using the apeer-ometiff-library
    omemd = omexmlClass.OMEXML(omexml_string)

    # create dictionary for metadata and get OME-XML data
    metadata = create_metadata_dict()

    # get directory and filename etc.
    metadata['Directory'] = os.path.dirname(filename)
    metadata['Filename'] = os.path.basename(filename)
    metadata['Extension'] = 'ome.tiff'
    metadata['ImageType'] = 'ometiff'
    metadata['AcqDate'] = omemd.image(series).AcquisitionDate
    metadata['Name'] = omemd.image(series).Name

    # get image dimensions TZCXY
    metadata['SizeT'] = omemd.image(series).Pixels.SizeT
    metadata['SizeZ'] = omemd.image(series).Pixels.SizeZ
    metadata['SizeC'] = omemd.image(series).Pixels.SizeC
    metadata['SizeX'] = omemd.image(series).Pixels.SizeX
    metadata['SizeY'] = omemd.image(series).Pixels.SizeY

    # get number of image series
    metadata['TotalSeries'] = omemd.get_image_count()
    metadata['Sizes BF'] = [metadata['TotalSeries'],
                            metadata['SizeT'],
                            metadata['SizeZ'],
                            metadata['SizeC'],
                            metadata['SizeY'],
                            metadata['SizeX']]

    # get dimension order
    metadata['DimOrder BF'] = omemd.image(series).Pixels.DimensionOrder

    # reverse the order to reflect later the array shape
    metadata['DimOrder BF Array'] = metadata['DimOrder BF'][::-1]

    # get the scaling
    metadata['XScale'] = omemd.image(series).Pixels.PhysicalSizeX
    # metadata['XScaleUnit'] = omemd.image(series).Pixels.PhysicalSizeXUnit
    metadata['YScale'] = omemd.image(series).Pixels.PhysicalSizeY
    # metadata['YScaleUnit'] = omemd.image(series).Pixels.PhysicalSizeYUnit
    metadata['ZScale'] = omemd.image(series).Pixels.PhysicalSizeZ
    # metadata['ZScaleUnit'] = omemd.image(series).Pixels.PhysicalSizeZUnit

    # get all image IDs
    for i in range(omemd.get_image_count()):
        metadata['ImageIDs'].append(i)

    # get information about the instrument and objective
    try:
        metadata['InstrumentID'] = omemd.instrument(series).get_ID()
    except (KeyError, AttributeError) as e:
        print('Key not found:', e)
        metadata['InstrumentID'] = None

    try:
        metadata['DetectorModel'] = omemd.instrument(series).Detector.get_Model()
        metadata['DetectorID'] = omemd.instrument(series).Detector.get_ID()
        metadata['DetectorModel'] = omemd.instrument(series).Detector.get_Type()
    except (KeyError, AttributeError) as e:
        print('Key not found:', e)
        metadata['DetectorModel'] = None
        metadata['DetectorID'] = None
        metadata['DetectorModel'] = None

    try:
        metadata['ObjNA'] = omemd.instrument(series).Objective.get_LensNA()
        metadata['ObjID'] = omemd.instrument(series).Objective.get_ID()
        metadata['ObjMag'] = omemd.instrument(series).Objective.get_NominalMagnification()
    except (KeyError, AttributeError) as e:
        print('Key not found:', e)
        metadata['ObjNA'] = None
        metadata['ObjID'] = None
        metadata['ObjMag'] = None

    # get channel names
    for c in range(metadata['SizeC']):
        metadata['Channels'].append(omemd.image(series).Pixels.Channel(c).Name)

    # add axes and shape information using aicsimageio package
    ometiff_aics = AICSImage(filename)
    metadata['Axes_aics'] = ometiff_aics.dims
    metadata['Shape_aics'] = ometiff_aics.shape
    metadata['SizeX_aics'] = ometiff_aics.size_x
    metadata['SizeY_aics'] = ometiff_aics.size_y
    metadata['SizeC_aics'] = ometiff_aics.size_c
    metadata['SizeZ_aics'] = ometiff_aics.size_t
    metadata['SizeT_aics'] = ometiff_aics.size_t
    metadata['SizeS_aics'] = ometiff_aics.size_s

    # close AICSImage object
    ometiff_aics.close()

    # check for None inside Scaling to avoid issues later one ...
    metadata = checkmdscale_none(metadata,
                                 tocheck=['XScale', 'YScale', 'ZScale'],
                                 replace=[1.0, 1.0, 1.0])

    return metadata


def checkmdscale_none(md, tocheck=['ZScale'], replace=[1.0]):
    """Check scaling entries for None to avoid issues later on

    :param md: original metadata
    :type md: dict
    :param tocheck: list with entries to check for None, defaults to ['ZScale']
    :type tocheck: list, optional
    :param replace: list with values replacing the None, defaults to [1.0]
    :type replace: list, optional
    :return: modified metadata where None entries where replaces by
    :rtype: [type]
    """
    for tc, rv in zip(tocheck, replace):
        if md[tc] is None:
            md[tc] = rv

    return md


def get_metadata_czi(filename, dim2none=False,
                     forceDim=False,
                     forceDimname='SizeC',
                     forceDimvalue=2):
    """
    Returns a dictionary with CZI metadata.

    Information CZI Dimension Characters:
    - '0': 'Sample',  # e.g. RGBA
    - 'X': 'Width',
    - 'Y': 'Height',
    - 'C': 'Channel',
    - 'Z': 'Slice',  # depth
    - 'T': 'Time',
    - 'R': 'Rotation',
    - 'S': 'Scene',  # contiguous regions of interest in a mosaic image
    - 'I': 'Illumination',  # direction
    - 'B': 'Block',  # acquisition
    - 'M': 'Mosaic',  # index of tile for compositing a scene
    - 'H': 'Phase',  # e.g. Airy detector fibers
    - 'V': 'View',  # e.g. for SPIM

    :param filename: filename of the CZI image
    :type filename: str
    :param dim2none: option to set non-existing dimension to None, defaults to False
    :type dim2none: bool, optional
    :return: metadata - dictionary with the relevant CZI metainformation
    :rtype: dict
    """

    # get CZI object
    czi = zis.CziFile(filename)

    # parse the XML into a dictionary
    metadatadict_czi = czi.metadata(raw=False)

    # initialize metadata dictionary
    metadata = create_metadata_dict()

    # get directory and filename etc.
    metadata['Directory'] = os.path.dirname(filename)
    metadata['Filename'] = os.path.basename(filename)
    metadata['Extension'] = 'czi'
    metadata['ImageType'] = 'czi'

    # add axes and shape information using czifile package
    metadata['Axes_czifile'] = czi.axes
    metadata['Shape_czifile'] = czi.shape

    # add axes and shape information using aicsimageio package
    czi_aics = AICSImage(filename)
    metadata['Axes_aics'] = czi_aics.dims
    try:
        metadata['Shape_aics'] = czi_aics.shape
        metadata['SizeX_aics'] = czi_aics.size_x
        metadata['SizeY_aics'] = czi_aics.size_y
        metadata['SizeC_aics'] = czi_aics.size_c
        metadata['SizeZ_aics'] = czi_aics.size_t
        metadata['SizeT_aics'] = czi_aics.size_t
        metadata['SizeS_aics'] = czi_aics.size_s
    except KeyError as e:
        metadata['Shape_aics'] = None
        metadata['SizeX_aics'] = None
        metadata['SizeY_aics'] = None
        metadata['SizeC_aics'] = None
        metadata['SizeZ_aics'] = None
        metadata['SizeT_aics'] = None
        metadata['SizeS_aics'] = None

    # get additional data by using pylibczi directly
    # Get the shape of the data, the coordinate pairs are (start index, size)
    aics_czi = CziFile(filename)
    metadata['dims_aicspylibczi'] = aics_czi.dims_shape()[0]
    metadata['dimorder_aicspylibczi'] = aics_czi.dims
    metadata['size_aicspylibczi'] = aics_czi.size
    metadata['czi_isMosaic'] = aics_czi.is_mosaic()

    # determine pixel type for CZI array
    metadata['NumPy.dtype'] = czi.dtype

    # check if the CZI image is an RGB image depending
    # on the last dimension entry of axes
    if czi.shape[-1] == 3:
        metadata['czi_isRGB'] = True

    try:
        metadata['PixelType'] = metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['PixelType']
    except KeyError as e:
        print('Key not found:', e)
        metadata['PixelType'] = None
    try:
        metadata['SizeX'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeX'])
    except KeyError as e:
        metadata['SizeX'] = None
    try:
        metadata['SizeY'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeY'])
    except KeyError as e:
        metadata['SizeY'] = None

    try:
        metadata['SizeZ'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeZ'])
    except Exception as e:
        # print('Exception:', e)
        if dim2none:
            metadata['SizeZ'] = None
        if not dim2none:
            metadata['SizeZ'] = 1

    # for special cases do not read the SizeC from the metadata
    if forceDim and forceDimname == 'SizeC':
        metadata[forceDimname] = forceDimvalue

    if not forceDim:

        try:
            metadata['SizeC'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeC'])
        except Exception as e:
            # print('Exception:', e)
            if dim2none:
                metadata['SizeC'] = None
            if not dim2none:
                metadata['SizeC'] = 1

    # create empty lists for channel related information
    channels = []
    channels_names = []
    channels_colors = []

    # in case of only one channel
    if metadata['SizeC'] == 1:
        # get name for dye
        try:
            channels.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                            ['Channels']['Channel']['ShortName'])
        except KeyError as e:
            print('Exception:', e)
            try:
                channels.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                ['Channels']['Channel']['DyeName'])
            except KeyError as e:
                print('Exception:', e)
                channels.append('Dye-CH1')

        # get channel name
        try:
            channels_names.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                  ['Channels']['Channel']['Name'])
        except KeyError as e:
            print('Exception:', e)
            channels_names.append['CH1']

        # get channel color
        try:
            channels_colors.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                   ['Channels']['Channel']['Color'])
        except KeyError as e:
            print('Exception:', e)
            channels_colors.append('#80808000')

    # in case of two or more channels
    if metadata['SizeC'] > 1:
        # loop over all channels
        for ch in range(metadata['SizeC']):
            # get name for dyes
            try:
                channels.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                                ['Channels']['Channel'][ch]['ShortName'])
            except KeyError as e:
                print('Exception:', e)
                try:
                    channels.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                                    ['Channels']['Channel'][ch]['DyeName'])
                except KeyError as e:
                    print('Exception:', e)
                    channels.append('Dye-CH' + str(ch))

            # get channel names
            try:
                channels_names.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                      ['Channels']['Channel'][ch]['Name'])
            except KeyError as e:
                print('Exception:', e)
                channels_names.append('CH' + str(ch))

            # get channel colors
            try:
                channels_colors.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                       ['Channels']['Channel'][ch]['Color'])
            except KeyError as e:
                print('Exception:', e)
                # use grayscale instead
                channels_colors.append('80808000')

    # write channels information (as lists) into metadata dictionary
    metadata['Channels'] = channels
    metadata['ChannelNames'] = channels_names
    metadata['ChannelColors'] = channels_colors

    try:
        metadata['SizeT'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeT'])
    except Exception as e:
        # print('Exception:', e)
        if dim2none:
            metadata['SizeT'] = None
        if not dim2none:
            metadata['SizeT'] = 1

    try:
        metadata['SizeM'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeM'])
    except Exception as e:
        # print('Exception:', e)
        if dim2none:
            metadata['SizeM'] = None
        if not dim2none:
            metadata['SizeM'] = 1

    try:
        metadata['SizeB'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeB'])
    except Exception as e:
        # print('Exception:', e)
        if dim2none:
            metadata['SizeB'] = None
        if not dim2none:
            metadata['SizeB'] = 1

    try:
        metadata['SizeS'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeS'])
    except Exception as e:
        # print('Exception:', e)
        if dim2none:
            metadata['SizeS'] = None
        if not dim2none:
            metadata['SizeS'] = 1

    try:
        metadata['SizeH'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeH'])
    except Exception as e:
        # print('Exception:', e)
        if dim2none:
            metadata['SizeH'] = None
        if not dim2none:
            metadata['SizeH'] = 1

    try:
        metadata['SizeI'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeI'])
    except Exception as e:
        # print('Exception:', e)
        if dim2none:
            metadata['SizeI'] = None
        if not dim2none:
            metadata['SizeI'] = 1

    try:
        metadata['SizeV'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeV'])
    except Exception as e:
        # print('Exception:', e)
        if dim2none:
            metadata['SizeV'] = None
        if not dim2none:
            metadata['SizeV'] = 1

    # get the scaling information
    try:
        # metadata['Scaling'] = metadatadict_czi['ImageDocument']['Metadata']['Scaling']
        metadata['XScale'] = float(metadatadict_czi['ImageDocument']['Metadata']['Scaling']['Items']['Distance'][0]['Value']) * 1000000
        metadata['YScale'] = float(metadatadict_czi['ImageDocument']['Metadata']['Scaling']['Items']['Distance'][1]['Value']) * 1000000
        # metadata['XScale'] = np.round(metadata['XScale'], 3)
        # metadata['YScale'] = np.round(metadata['YScale'], 3)
        try:
            metadata['XScaleUnit'] = metadatadict_czi['ImageDocument']['Metadata']['Scaling']['Items']['Distance'][0]['DefaultUnitFormat']
            metadata['YScaleUnit'] = metadatadict_czi['ImageDocument']['Metadata']['Scaling']['Items']['Distance'][1]['DefaultUnitFormat']
        except KeyError as e:
            print('Key not found:', e)
            metadata['XScaleUnit'] = None
            metadata['YScaleUnit'] = None
        try:
            metadata['ZScale'] = float(metadatadict_czi['ImageDocument']['Metadata']['Scaling']['Items']['Distance'][2]['Value']) * 1000000
            # metadata['ZScale'] = np.round(metadata['ZScale'], 3)
            try:
                metadata['ZScaleUnit'] = metadatadict_czi['ImageDocument']['Metadata']['Scaling']['Items']['Distance'][2]['DefaultUnitFormat']
            except KeyError as e:
                print('Key not found:', e)
                metadata['ZScaleUnit'] = metadata['XScaleUnit']
        except Exception as e:
            # print('Exception:', e)
            if dim2none:
                metadata['ZScale'] = None
                metadata['ZScaleUnit'] = None
            if not dim2none:
                # set to isotropic scaling if it was single plane only
                metadata['ZScale'] = metadata['XScale']
                metadata['ZScaleUnit'] = metadata['XScaleUnit']
    except Exception as e:
        print('Exception:', e)
        print('Scaling Data could not be found.')

    # try to get software version
    try:
        metadata['SW-Name'] = metadatadict_czi['ImageDocument']['Metadata']['Information']['Application']['Name']
        metadata['SW-Version'] = metadatadict_czi['ImageDocument']['Metadata']['Information']['Application']['Version']
    except KeyError as e:
        print('Key not found:', e)
        metadata['SW-Name'] = None
        metadata['SW-Version'] = None

    try:
        metadata['AcqDate'] = metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['AcquisitionDateAndTime']
    except KeyError as e:
        print('Key not found:', e)
        metadata['AcqDate'] = None

    # get objective data
    try:
        metadata['ObjName'] = metadatadict_czi['ImageDocument']['Metadata']['Information']['Instrument']['Objectives']['Objective']['Name']
    except KeyError as e:
        print('Key not found:', e)
        metadata['ObjName'] = None

    try:
        metadata['ObjImmersion'] = metadatadict_czi['ImageDocument']['Metadata']['Information']['Instrument']['Objectives']['Objective']['Immersion']
    except KeyError as e:
        print('Key not found:', e)
        metadata['ObjImmersion'] = None

    try:
        metadata['ObjNA'] = np.float(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                     ['Instrument']['Objectives']['Objective']['LensNA'])
    except KeyError as e:
        print('Key not found:', e)
        metadata['ObjNA'] = None

    try:
        metadata['ObjID'] = metadatadict_czi['ImageDocument']['Metadata']['Information']['Instrument']['Objectives']['Objective']['Id']
    except KeyError as e:
        print('Key not found:', e)
        metadata['ObjID'] = None

    try:
        metadata['TubelensMag'] = np.float(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                           ['Instrument']['TubeLenses']['TubeLens']['Magnification'])
    except KeyError as e:
        print('Key not found:', e, 'Using Default Value = 1.0 for Tublens Magnification.')
        metadata['TubelensMag'] = 1.0

    try:
        metadata['ObjNominalMag'] = np.float(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                             ['Instrument']['Objectives']['Objective']['NominalMagnification'])
    except KeyError as e:
        print('Key not found:', e, 'Using Default Value = 1.0 for Nominal Magnification.')
        metadata['ObjNominalMag'] = 1.0

    try:
        if metadata['TubelensMag'] is not None:
            metadata['ObjMag'] = metadata['ObjNominalMag'] * metadata['TubelensMag']
        if metadata['TubelensMag'] is None:
            print('No TublensMag found. Use 1 instead')
            metadata['ObjMag'] = metadata['ObjNominalMag'] * 1.0

    except KeyError as e:
        print('Key not found:', e)
        metadata['ObjMag'] = None

    # get detector information

    # check if there are any detector entries inside the dictionary
    if pydash.objects.has(metadatadict_czi, ['ImageDocument', 'Metadata', 'Information', 'Instrument', 'Detectors']):

        if isinstance(metadatadict_czi['ImageDocument']['Metadata']['Information']['Instrument']['Detectors']['Detector'], list):
            num_detectors = len(metadatadict_czi['ImageDocument']['Metadata']['Information']['Instrument']['Detectors']['Detector'])
        else:
            num_detectors = 1

        # if there is only one detector found
        if num_detectors == 1:

            # check for detector ID
            try:
                metadata['DetectorID'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                              ['Instrument']['Detectors']['Detector']['Id'])
            except KeyError as e:
                metadata['DetectorID'].append(None)

            # check for detector Name
            try:
                metadata['DetectorName'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                ['Instrument']['Detectors']['Detector']['Name'])
            except KeyError as e:
                metadata['DetectorName'].append(None)

            # check for detector model
            try:
                metadata['DetectorModel'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                 ['Instrument']['Detectors']['Detector']['Manufacturer']['Model'])
            except KeyError as e:
                metadata['DetectorModel'].append(None)

            # check for detector type
            try:
                metadata['DetectorType'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                ['Instrument']['Detectors']['Detector']['Type'])
            except KeyError as e:
                metadata['DetectorType'].append(None)

        if num_detectors > 1:
            for d in range(num_detectors):

                # check for detector ID
                try:
                    metadata['DetectorID'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                  ['Instrument']['Detectors']['Detector'][d]['Id'])
                except KeyError as e:
                    metadata['DetectorID'].append(None)

                # check for detector Name
                try:
                    metadata['DetectorName'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                    ['Instrument']['Detectors']['Detector'][d]['Name'])
                except KeyError as e:
                    metadata['DetectorName'].append(None)

                # check for detector model
                try:
                    metadata['DetectorModel'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                     ['Instrument']['Detectors']['Detector'][d]['Manufacturer']['Model'])
                except KeyError as e:
                    metadata['DetectorModel'].append(None)

                # check for detector type
                try:
                    metadata['DetectorType'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                    ['Instrument']['Detectors']['Detector'][d]['Type'])
                except KeyError as e:
                    metadata['DetectorType'].append(None)

    # check for well information
    metadata['Well_ArrayNames'] = []
    metadata['Well_Indices'] = []
    metadata['Well_PositionNames'] = []
    metadata['Well_ColId'] = []
    metadata['Well_RowId'] = []
    metadata['WellCounter'] = None
    metadata['SceneStageCenterX'] = []
    metadata['SceneStageCenterY'] = []

    try:
        print('Trying to extract Scene and Well information if existing ...')
        # extract well information from the dictionary
        allscenes = metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['Dimensions']['S']['Scenes']['Scene']

        # loop over all detected scenes
        for s in range(metadata['SizeS']):

            if metadata['SizeS'] == 1:
                well = allscenes
                try:
                    metadata['Well_ArrayNames'].append(allscenes['ArrayName'])
                except KeyError as e:
                    # print('Key not found in Metadata Dictionary:', e)
                    try:
                        metadata['Well_ArrayNames'].append(well['Name'])
                    except KeyError as e:
                        print('Key not found in Metadata Dictionary:', e, 'Using A1 instead')
                        metadata['Well_ArrayNames'].append('A1')

                try:
                    metadata['Well_Indices'].append(allscenes['Index'])
                except KeyError as e:
                    print('Key not found in Metadata Dictionary:', e)
                    metadata['Well_Indices'].append(1)

                try:
                    metadata['Well_PositionNames'].append(allscenes['Name'])
                except KeyError as e:
                    print('Key not found in Metadata Dictionary:', e)
                    metadata['Well_PositionNames'].append('P1')

                try:
                    metadata['Well_ColId'].append(np.int(allscenes['Shape']['ColumnIndex']))
                except KeyError as e:
                    print('Key not found in Metadata Dictionary:', e)
                    metadata['Well_ColId'].append(0)

                try:
                    metadata['Well_RowId'].append(np.int(allscenes['Shape']['RowIndex']))
                except KeyError as e:
                    print('Key not found in Metadata Dictionary:', e)
                    metadata['Well_RowId'].append(0)

                try:
                    # count the content of the list, e.g. how many time a certain well was detected
                    metadata['WellCounter'] = Counter(metadata['Well_ArrayNames'])
                except KeyError as e:
                    print('Key not found in Metadata Dictionary:', e)
                    metadata['WellCounter'].append(Counter({'A1': 1}))

                try:
                    # get the SceneCenter Position
                    sx = allscenes['CenterPosition'].split(',')[0]
                    sy = allscenes['CenterPosition'].split(',')[1]
                    metadata['SceneStageCenterX'].append(np.double(sx))
                    metadata['SceneStageCenterY'].append(np.double(sy))
                except KeyError as e:
                    metadata['SceneStageCenterX'].append(0.0)
                    metadata['SceneStageCenterY'].append(0.0)

            if metadata['SizeS'] > 1:
                try:
                    well = allscenes[s]
                    metadata['Well_ArrayNames'].append(well['ArrayName'])
                except KeyError as e:
                    # print('Key not found in Metadata Dictionary:', e)
                    try:
                        metadata['Well_ArrayNames'].append(well['Name'])
                    except KeyError as e:
                        print('Key not found in Metadata Dictionary:', e, 'Using A1 instead')
                        metadata['Well_ArrayNames'].append('A1')

                # get the well information
                try:
                    metadata['Well_Indices'].append(well['Index'])
                except KeyError as e:
                    # print('Key not found in Metadata Dictionary:', e)
                    metadata['Well_Indices'].append(None)
                try:
                    metadata['Well_PositionNames'].append(well['Name'])
                except KeyError as e:
                    # print('Key not found in Metadata Dictionary:', e)
                    metadata['Well_PositionNames'].append(None)

                try:
                    metadata['Well_ColId'].append(np.int(well['Shape']['ColumnIndex']))
                except KeyError as e:
                    print('Key not found in Metadata Dictionary:', e)
                    metadata['Well_ColId'].append(None)

                try:
                    metadata['Well_RowId'].append(np.int(well['Shape']['RowIndex']))
                except KeyError as e:
                    print('Key not found in Metadata Dictionary:', e)
                    metadata['Well_RowId'].append(None)

                # count the content of the list, e.g. how many time a certain well was detected
                metadata['WellCounter'] = Counter(metadata['Well_ArrayNames'])

                # try:
                if isinstance(allscenes, list):
                    try:
                        # get the SceneCenter Position
                        sx = allscenes[s]['CenterPosition'].split(',')[0]
                        sy = allscenes[s]['CenterPosition'].split(',')[1]
                        metadata['SceneStageCenterX'].append(np.double(sx))
                        metadata['SceneStageCenterY'].append(np.double(sy))
                    except KeyError as e:
                        print('Key not found in Metadata Dictionary:', e)
                        metadata['SceneCenterX'].append(0.0)
                        metadata['SceneCenterY'].append(0.0)
                if not isinstance(allscenes, list):
                    metadata['SceneStageCenterX'].append(0.0)
                    metadata['SceneStageCenterY'].append(0.0)

            # count the number of different wells
            metadata['NumWells'] = len(metadata['WellCounter'].keys())

    except (KeyError, TypeError) as e:
        print('No valid Scene or Well information found:', e)

    # close CZI file
    czi.close()

    # close AICSImage object
    czi_aics.close()

    return metadata


def get_additional_metadata_czi(filename):
    """
    Returns a dictionary with additional CZI metadata.

    :param filename: filename of the CZI image
    :type filename: str
    :return: additional_czimd - dictionary with additional CZI metainformation
    :rtype: dict
    """

    # get CZI object and read array
    czi = zis.CziFile(filename)

    # parse the XML into a dictionary
    metadatadict_czi = xmltodict.parse(czi.metadata())
    additional_czimd = {}

    try:
        additional_czimd['Experiment'] = metadatadict_czi['ImageDocument']['Metadata']['Experiment']
    except KeyError as e:
        print('Key not found:', e)
        additional_czimd['Experiment'] = None

    try:
        additional_czimd['HardwareSetting'] = metadatadict_czi['ImageDocument']['Metadata']['HardwareSetting']
    except KeyError as e:
        print('Key not found:', e)
        additional_czimd['HardwareSetting'] = None

    try:
        additional_czimd['CustomAttributes'] = metadatadict_czi['ImageDocument']['Metadata']['CustomAttributes']
    except KeyError as e:
        print('Key not found:', e)
        additional_czimd['CustomAttributes'] = None

    try:
        additional_czimd['DisplaySetting'] = metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
    except KeyError as e:
        print('Key not found:', e)
        additional_czimd['DisplaySetting'] = None

    try:
        additional_czimd['Layers'] = metadatadict_czi['ImageDocument']['Metadata']['Layers']
    except KeyError as e:
        print('Key not found:', e)
        additional_czimd['Layers'] = None

    # close CZI file
    czi.close()

    return additional_czimd


def md2dataframe(metadata, paramcol='Parameter', keycol='Value'):
    """Convert the metadata dictionary to a Pandas DataFrame.

    :param metadata: MeteData dictionary
    :type metadata: dict
    :param paramcol: Name of Columns for the MetaData Parameters, defaults to 'Parameter'
    :type paramcol: str, optional
    :param keycol: Name of Columns for the MetaData Values, defaults to 'Value'
    :type keycol: str, optional
    :return: Pandas DataFrame containing all the metadata
    :rtype: Pandas.DataFrame
    """
    mdframe = pd.DataFrame(columns=[paramcol, keycol])

    for k in metadata.keys():
        d = {'Parameter': k, 'Value': metadata[k]}
        df = pd.DataFrame([d], index=[0])
        mdframe = pd.concat([mdframe, df], ignore_index=True)

    return mdframe


def get_dimorder(dimstring):
    """Get the order of dimensions from dimension string

    :param dimstring: string containing the dimensions
    :type dimstring: str
    :return: dims_dict - dictionary with the dimensions and its positions
    :rtype: dict
    :return: dimindex_list - list with indices of dimensions
    :rtype: list
    :return: numvalid_dims - number of valid dimensions
    :rtype: integer
    """

    dimindex_list = []
    dims = ['R', 'I', 'M', 'H', 'V', 'B', 'S', 'T', 'C', 'Z', 'Y', 'X', '0']
    dims_dict = {}

    # loop over all dimensions and find the index
    for d in dims:

        dims_dict[d] = dimstring.find(d)
        dimindex_list.append(dimstring.find(d))

    # check if a dimension really exists
    numvalid_dims = sum(i > 0 for i in dimindex_list)

    return dims_dict, dimindex_list, numvalid_dims


def get_array_czi(filename,
                  replace_value=False,
                  remove_HDim=True,
                  return_addmd=False,
                  forceDim=False,
                  forceDimname='SizeC',
                  forceDimvalue=2):
    """Get the pixel data of the CZI file as multidimensional NumPy.Array

    :param filename: filename of the CZI file
    :type filename: str
    :param replacevalue: replace arrays entries with a specific value with NaN, defaults to False
    :type replacevalue: bool, optional
    :param remove_HDim: remove the H-Dimension (Airy Scan Detectors), defaults to True
    :type remove_HDim: bool, optional
    :param return_addmd: read the additional metadata, defaults to False
    :type return_addmd: bool, optional
    :param forceDim: force a specfic dimension to have a specif value, defaults to False
    :type forceDim: bool, optional
    :param forceDimname: name of the dimension, defaults to 'SizeC'
    :type forceDimname: str, optional
    :param forceDimvalue: value of the dimension, defaults to 2
    :type forceDimvalue: int, optional
    :return: cziarray - dictionary with the dimensions and its positions
    :rtype: NumPy.Array
    :return: metadata - dictionary with CZI metadata
    :rtype: dict
    :return: additional_metadata_czi - dictionary with additional CZI metadata
    :rtype: dict
    """

    metadata = get_metadata_czi(filename,
                                forceDim=forceDim,
                                forceDimname=forceDimname,
                                forceDimvalue=forceDimvalue)

    # get additional metainformation
    additional_metadata_czi = get_additional_metadata_czi(filename)

    # get CZI object and read array
    czi = zis.CziFile(filename)
    cziarray = czi.asarray()

    # check for H dimension and remove
    if remove_HDim and metadata['Axes_czifile'][0] == 'H':
        # metadata['Axes'] = metadata['Axes_czifile'][1:]
        metadata['Axes_czifile'] = metadata['Axes_czifile'].replace('H', '')
        cziarray = np.squeeze(cziarray, axis=0)

    # get additional information about dimension order etc.
    dim_dict, dim_list, numvalid_dims = get_dimorder(metadata['Axes_czifile'])
    metadata['DimOrder CZI'] = dim_dict

    if cziarray.shape[-1] == 3:
        pass
    else:
        # remove the last dimension from the end
        cziarray = np.squeeze(cziarray, axis=len(metadata['Axes_czifile']) - 1)
        metadata['Axes_czifile'] = metadata['Axes_czifile'].replace('0', '')

    if replace_value:
        cziarray = replace_value(cziarray, value=0)

    # close czi file
    czi.close()

    return cziarray, metadata, additional_metadata_czi


def replace_value(data, value=0):
    """Replace specifc values in array with NaN

    :param data: Array where values should be replaced
    :type data: NumPy.Array
    :param value: value inside array to be replaced with NaN, defaults to 0
    :type value: int, optional
    :return: array with new values
    :rtype: NumPy.Array
    """

    data = data.astype('float')
    data[data == value] = np.nan

    return data


def get_scalefactor(metadata):
    """Add scaling factors to the metadata dictionary

    :param metadata: dictionary with CZI or OME-TIFF metadata
    :type metadata: dict
    :return: dictionary with additional keys for scling factors
    :rtype: dict
    """

    # set default scale factor to 1.0
    scalefactors = {'xy': 1.0,
                    'zx': 1.0
                    }

    try:
        # get the factor between XY scaling
        scalefactors['xy'] = np.round(metadata['XScale'] / metadata['YScale'], 3)
        # get the scalefactor between XZ scaling
        scalefactors['zx'] = np.round(metadata['ZScale'] / metadata['YScale'], 3)
    except KeyError as e:
        print('Key not found: ', e, 'Using defaults = 1.0')

    return scalefactors


def calc_scaling(data, corr_min=1.0,
                 offset_min=0,
                 corr_max=0.85,
                 offset_max=0):
    """[summary]

    :param data: Calculate min / max scaling
    :type data: Numpy.Array
    :param corr_min: correction factor for minvalue, defaults to 1.0
    :type corr_min: float, optional
    :param offset_min: offset for min value, defaults to 0
    :type offset_min: int, optional
    :param corr_max: correction factor for max value, defaults to 0.85
    :type corr_max: float, optional
    :param offset_max: offset for max value, defaults to 0
    :type offset_max: int, optional
    :return: list with [minvalue, maxvalue]
    :rtype: list
    """

    # get min-max values for initial scaling
    minvalue = np.round((data.min() + offset_min) * corr_min)
    maxvalue = np.round((data.max() + offset_max) * corr_max)
    print('Scaling: ', minvalue, maxvalue)

    return [minvalue, maxvalue]


def show_napari(array, metadata,
                blending='additive',
                gamma=0.85,
                add_mdtable=True,
                rename_sliders=False):
    """Show the multidimensional array using the Napari viewer

    :param array: multidimensional NumPy.Array containing the pixeldata
    :type array: NumPy.Array
    :param metadata: dictionary with CZI or OME-TIFF metadata
    :type metadata: dict
    :param blending: NapariViewer option for blending, defaults to 'additive'
    :type blending: str, optional
    :param gamma: NapariViewer value for Gamma, defaults to 0.85
    :type gamma: float, optional
    :param rename_sliders: name slider with correct labels output, defaults to False
    :type verbose: bool, optional
    """

    class TableWidget(QWidget):

        def __init__(self):
            super(QWidget, self).__init__()
            self.layout = QHBoxLayout(self)
            self.mdtable = QTableWidget()
            self.layout.addWidget(self.mdtable)
            self.mdtable.setShowGrid(True)
            self.mdtable.setHorizontalHeaderLabels(['Parameter', 'Value'])
            header = self.mdtable.horizontalHeader()
            header.setDefaultAlignment(Qt.AlignLeft)

        def update_metadata(self, md):

            row_count = len(md)
            col_count = 2

            self.mdtable.setColumnCount(col_count)
            self.mdtable.setRowCount(row_count)

            row = 0

            for key, value in md.items():
                newkey = QTableWidgetItem(key)
                self.mdtable.setItem(row, 0, newkey)
                newvalue = QTableWidgetItem(str(value))
                self.mdtable.setItem(row, 1, newvalue)
                row += 1

            # fit columns to content
            self.mdtable.resizeColumnsToContents()

        def update_style(self):

            fnt = QFont()
            fnt.setPointSize(11)
            fnt.setBold(True)
            fnt.setFamily("Arial")

            item1 = QtWidgets.QTableWidgetItem('Parameter')
            item1.setForeground(QtGui.QColor(25, 25, 25))
            item1.setFont(fnt)
            self.mdtable.setHorizontalHeaderItem(0, item1)
            item2 = QtWidgets.QTableWidgetItem('Value')
            item2.setForeground(QtGui.QColor(25, 25, 25))
            item2.setFont(fnt)
            self.mdtable.setHorizontalHeaderItem(1, item2)

    # create list for the napari layers
    napari_layers = []

    with napari.gui_qt():

        # create scalefcator with all ones
        scalefactors = [1.0] * len(array.shape)
        dimpos = get_dimpositions(metadata['Axes_aics'])

        # get the scalefactors from the metadata
        scalef = get_scalefactor(metadata)

        # modify the tuple for the scales for napari
        scalefactors[dimpos['Z']] = scalef['zx']

        # remove C dimension from scalefactor
        scalefactors_ch = scalefactors.copy()
        del scalefactors_ch[dimpos['C']]

        # initialize the napari viewer
        print('Initializing Napari Viewer ...')

        # create a viewer and add some images
        viewer = napari.Viewer()

        # add widget for metadata
        if add_mdtable:

            # create widget for the metadata
            mdbrowser = TableWidget()

            viewer.window.add_dock_widget(mdbrowser,
                                          name='mdbrowser',
                                          area='right')

            # add the metadata and adapt the table display
            mdbrowser.update_metadata(metadata)
            mdbrowser.update_style()

        if metadata['SizeC'] > 1:

            # add all channels as layers
            for ch in range(metadata['SizeC']):

                try:
                    # get the channel name
                    chname = metadata['Channels'][ch]
                except KeyError as e:
                    print(e)
                    # or use CH1 etc. as string for the name
                    chname = 'CH' + str(ch + 1)

                # cut out channel
                # use dask if array is a dask.array
                if isinstance(array, da.Array):
                    print('Extract Channel using Dask.Array')
                    channel = array.compute().take(ch, axis=dimpos['C'])
                    new_dimstring = metadata['Axes_aics'].replace('C', '')

                else:
                    # use normal numpy if not
                    print('Extract Channel NumPy.Array')
                    channel = array.take(ch, axis=dimpos['C'])
                    new_dimstring = metadata['Axes_aics'].replace('C', '')

                # actually show the image array
                print('Adding Channel  : ', chname)
                print('Shape Channel   : ', ch, channel.shape)
                print('Scaling Factors : ', scalefactors_ch)

                # get min-max values for initial scaling
                clim = calc_scaling(channel,
                                    corr_min=1.0,
                                    offset_min=0,
                                    corr_max=0.85,
                                    offset_max=0)

                # add channel to napari viewer
                new_layer = viewer.add_image(channel,
                                             name=chname,
                                             scale=scalefactors_ch,
                                             contrast_limits=clim,
                                             blending=blending,
                                             gamma=gamma)

                napari_layers.append(new_layer)

        if metadata['SizeC'] == 1:

            # just add one channel as a layer
            try:
                # get the channel name
                chname = metadata['Channels'][0]
            except KeyError:
                # or use CH1 etc. as string for the name
                chname = 'CH' + str(ch + 1)

            # actually show the image array
            print('Adding Channel: ', chname)
            print('Scaling Factors: ', scalefactors)

            # get min-max values for initial scaling
            clim = calc_scaling(array)

            # add layer to Napari viewer
            new_layer = viewer.add_image(array,
                                         name=chname,
                                         scale=scalefactors,
                                         contrast_limits=clim,
                                         blending=blending,
                                         gamma=gamma)

            napari_layers.append(new_layer)

        if rename_sliders:

            print('Renaming the Sliders based on the Dimension String ....')

            # get the position of dimension entries after removing C dimension
            dimpos_viewer = get_dimpositions(new_dimstring)

            # get the label of the sliders
            sliders = viewer.dims.axis_labels

            # update the labels with the correct dimension strings
            slidernames = ['B', 'S', 'T', 'Z']
            for s in slidernames:
                if dimpos_viewer[s] >= 0:
                    sliders[dimpos_viewer[s]] = s
            # apply the new labels to the viewer
            viewer.dims.axis_labels = sliders

    return napari_layers


def check_for_previewimage(czi):
    """Check if the CZI contains an image from a prescan camera

    :param czi: CZI imagefile object
    :type metadata: CziFile object
    :return: has_attimage - Boolean if CZI image contains prescan image
    :rtype: bool
    """

    att = []

    # loop over the attachments
    for attachment in czi.attachments():
        entry = attachment.attachment_entry
        print(entry.name)
        att.append(entry.name)

    has_attimage = False

    # check for the entry "SlidePreview"
    if 'SlidePreview' in att:
        has_attimage = True

    return has_attimage


def writexml_czi(filename, xmlsuffix='_CZI_MetaData.xml'):
    """Write XML imformation of CZI to disk

    :param filename: CZI image filename
    :type filename: str
    :param xmlsuffix: suffix for the XML file that will be created, defaults to '_CZI_MetaData.xml'
    :type xmlsuffix: str, optional
    :return: filename of the XML file
    :rtype: str
    """

    # open czi file and get the metadata
    czi = zis.CziFile(filename)
    mdczi = czi.metadata()
    czi.close()

    # change file name
    xmlfile = filename.replace('.czi', xmlsuffix)

    # get tree from string
    tree = ET.ElementTree(ET.fromstring(mdczi))

    # write XML file to same folder
    tree.write(xmlfile, encoding='utf-8', method='xml')

    return xmlfile


def writexml_ometiff(filename, xmlsuffix='_OMETIFF_MetaData.xml'):
    """Write XML imformation of OME-TIFF to disk

    :param filename: OME-TIFF image filename
    :type filename: str
    :param xmlsuffix: suffix for the XML file that will be created, defaults to '_OMETIFF_MetaData.xml'
    :type xmlsuffix: str, optional
    :return: filename of the XML file
    :rtype: str
    """

    if filename.lower().endswith('.ome.tiff'):
        ext = '.ome.tiff'
    if filename.lower().endswith('.ome.tif'):
        ext = '.ome.tif'

    with tifffile.TiffFile(filename) as tif:
        # omexml_string = tif[0].image_description.decode('utf-8')
        omexml_string = tif[0].image_description

    # get tree from string
    # tree = ET.ElementTree(ET.fromstring(omexml_string.encode('utf-8')))
    tree = ET.ElementTree(ET.fromstring(omexml_string))

    # change file name
    xmlfile = filename.replace(ext, xmlsuffix)

    tree.write(xmlfile, encoding='utf-8', method='xml', pretty_print=True)
    print('Created OME-XML file for testdata: ', filename)

    return xmlfile


def getImageSeriesIDforWell(welllist, wellID):
    """
    Returns all ImageSeries (for OME-TIFF) indicies for a specific wellID

    :param welllist: list containing all wellIDs as stringe, e.g. '[B4, B4, B4, B4, B5, B5, B5, B5]'
    :type welllist: list
    :param wellID: string specifying the well, eg.g. 'B4'
    :type wellID: str
    :return: imageseriesindices - list containing all ImageSeries indices, which correspond the the well
    :rtype: list
    """

    imageseries_indices = [i for i, x in enumerate(welllist) if x == wellID]

    return imageseries_indices


def addzeros(number):
    """Convert a number into a string and add leading zeros.
    Typically used to construct filenames with equal lengths.

    :param number: the number
    :type number: int
    :return: zerostring - string with leading zeros
    :rtype: str
    """

    if number < 10:
        zerostring = '0000' + str(number)
    if number >= 10 and number < 100:
        zerostring = '000' + str(number)
    if number >= 100 and number < 1000:
        zerostring = '00' + str(number)
    if number >= 1000 and number < 10000:
        zerostring = '0' + str(number)

    return zerostring


def get_fname_woext(filepath):
    """Get the complete path of a file without the extension
    It alos will works for extensions like c:\myfile.abc.xyz
    The output will be: c:\myfile

    :param filepath: complete fiepath
    :type filepath: str
    :return: complete filepath without extension
    :rtype: str
    """
    # create empty string
    real_extension = ''

    # get all part of the file extension
    sufs = Path(filepath).suffixes
    for s in sufs:
        real_extension = real_extension + s

    # remover real extension from filepath
    filepath_woext = filepath.replace(real_extension, '')

    return filepath_woext


def get_dimpositions(dimstring, tocheck=['B', 'S', 'T', 'Z', 'C']):
    """Simple function to get the indices of the dimension identifiers in a string

    :param dimstring: dimension string
    :type dimstring: str
    :param tocheck: list of entries to check, defaults to ['B', 'S', 'T', 'Z', 'C']
    :type tocheck: list, optional
    :return: dictionary with positions of dimensions inside string
    :rtype: dict
    """
    dimpos = {}
    for p in tocheck:
        dimpos[p] = dimstring.find(p)

    return dimpos


def norm_columns(df, colname='Time [s]', mode='min'):
    """Normalize a specif column inside a Pandas dataframe

    :param df: DataFrame
    :type df: pf.DataFrame
    :param colname: Name of the coumn to be normalized, defaults to 'Time [s]'
    :type colname: str, optional
    :param mode: Mode of Normalization, defaults to 'min'
    :type mode: str, optional
    :return: Dataframe with normalized column
    :rtype: pd.DataFrame
    """
    # normalize columns according to min or max value
    if mode == 'min':
        min_value = df[colname].min()
        df[colname] = df[colname] - min_value

    if mode == 'max':
        max_value = df[colname].max()
        df[colname] = df[colname] - max_value

    return df


def getdims_pylibczi(czi):

    # Get the shape of the data, the coordinate pairs are (start index, size)
    # [{'X': (0, 1900), 'Y': (0, 1300), 'Z': (0, 60), 'C': (0, 4), 'S': (0, 40), 'B': (0, 1)}]
    # dimensions = czi.dims_shape()

    dimsizes = {}
    for d in range(len(czi.dims)):
        # print(d)
        dimsizes['Size' + czi.dims[d]] = czi.size[d]

    return dimsizes
