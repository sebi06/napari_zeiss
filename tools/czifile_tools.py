# -*- coding: utf-8 -*-

#################################################################
# File        : czifile_tools.py
# Version     : 0.0.2
# Author      : czsrh
# Date        : 09.06.2021
# Institution : Carl Zeiss Microscopy GmbH
#
# Disclaimer: This tool is purely experimental. Feel free to
# use it at your own risk.
#
# Copyright (c) 2021 Carl Zeiss AG, Germany. All Rights Reserved.
#################################################################

import os
import sys
from pathlib import Path
import xmltodict
from collections import Counter
import xml.etree.ElementTree as ET
from aicspylibczi import CziFile
import pydash
import zarr
import itertools as it
from tqdm.contrib.itertools import product
import pandas as pd
import numpy as np
from datetime import datetime
import dateutil.parser as dt
from lxml import etree


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
                'SizeX': None,
                'SizeY': None,
                'SizeZ': 1,
                'SizeC': 1,
                'SizeT': 1,
                'SizeS': 1,
                'SizeB': 1,
                'SizeM': 1,
                'isRGB': False,
                'isMosaic': False,
                'czi_size': None,
                'czi_dims': None,
                'czi_dims_shape': None,
                'ObjNA': [],
                'ObjMag': [],
                'ObjID': [],
                'ObjName': [],
                'ObjImmersion': [],
                'TubelensMag': [],
                'ObjNominalMag': [],
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
                'bbox_all_scenes': None,
                'bbox_all_mosaic_scenes': None,
                'bbox_all_mosaic_tiles': None,
                'bbox_all_tiles': None
                }

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
                     forceDimvalue=2,
                     convert_scunit=True):
    """
    Returns a dictionary with CZI metadata.

    Information CZI Dimension Characters:
    - '0':'Sample',  # e.g. RGBA
    - 'X':'Width',
    - 'Y':'Height',
    - 'C':'Channel',
    - 'Z':'Slice',  # depth
    - 'T':'Time',
    - 'R':'Rotation',
    - 'S':'Scene',  # contiguous regions of interest in a mosaic image
    - 'I':'Illumination',  # direction
    - 'B':'Block',  # acquisition
    - 'M':'Mosaic',  # index of tile for compositing a scene
    - 'H':'Phase',  # e.g. Airy detector fibers
    - 'V':'View',  # e.g. for SPIM

    :param filename: filename of the CZI image
    :type filename: str
    :param dim2none: option to set non-existing dimension to None, defaults to False
    :type dim2none: bool, optional
    :param forceDim: option to force to not read certain dimensions, defaults to False
    :type forceDim: bool, optional
    :param forceDimname: name of the dimension not to read, defaults to SizeC
    :type forceDimname: str, optional
    :param forceDimvalue: index of the dimension not to read, defaults to 2
    :type forceDimvalue: int, optional
    :param convert_scunit: convert scale unit string from 'µm' to 'micron', defaults to False
    :type convert_scunit: bool, optional
    :return: metadata, metadata_add - dictionaries with the relevant CZI metainformation
    :rtype: dict
    """

    # get metadata dictionary using aicspylibczi
    czi = CziFile(filename)
    xmlstr = ET.tostring(czi.meta)
    metadatadict_czi = xmltodict.parse(xmlstr)

    # initialize metadata dictionary
    metadata = create_metadata_dict()

    # get directory and filename etc.
    metadata['Directory'] = os.path.dirname(filename)
    metadata['Filename'] = os.path.basename(filename)
    metadata['Extension'] = 'czi'
    metadata['ImageType'] = 'czi'

    # get additional data by using pylibczi directly
    metadata['czi_dims'] = czi.dims
    metadata['czi_dims_shape'] = czi.get_dims_shape()
    metadata['czi_size'] = czi.size
    metadata['isMosaic'] = czi.is_mosaic()
    print('CZI is Mosaic :', metadata['isMosaic'])

    metadata = checkdims_czi(czi, metadata)

    # determine pixel type for CZI array using aicspylibczi
    metadata['Pixeltype_aics'] = czi.pixel_type
    # determine pixel type for CZI array
    metadata['NumPy.dtype'] = get_dtype_fromstring(czi.pixel_type)

    if 'A' in czi.dims:
        metadata['isRGB'] = True
    print('CZI is RGB :', metadata['isRGB'])

    # determine pixel type for CZI array by reading XML metadata
    try:
        metadata['PixelType'] = metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['PixelType']
    except KeyError as e:
        print('No PixelType :', e)
        metadata['PixelType'] = None
    try:
        metadata['SizeX'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeX'])
    except KeyError as e:
        print('No X Dimension :', e)
        metadata['SizeX'] = None
    try:
        metadata['SizeY'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeY'])
    except KeyError as e:
        print('No Y Dimension :', e)
        metadata['SizeY'] = None

    try:
        metadata['SizeZ'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeZ'])
    except KeyError as e:
        print('No Z Dimension :', e)
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
        except KeyError as e:
            print('No C Dimension :', e)
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
            print('Channel shortname not found :', e)
            try:
                channels.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                ['Channels']['Channel']['DyeName'])
            except KeyError as e:
                print('Channel dye not found :', e)
                channels.append('Dye-CH1')

        # get channel name
        try:
            channels_names.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                  ['Channels']['Channel']['Name'])
        except KeyError as e:
            try:
                channels_names.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                      ['Channels']['Channel']['@Name'])
            except KeyError as e:
                print('Channel name found :', e)
                channels_names.append('CH1')

        # get channel color
        try:
            channels_colors.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                   ['Channels']['Channel']['Color'])
        except KeyError as e:
            print('Channel color not found :', e)
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
                print('Channel shortname not found :', e)
                try:
                    channels.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                                    ['Channels']['Channel'][ch]['DyeName'])
                except KeyError as e:
                    print('Channel dye not found :', e)
                    channels.append('Dye-CH' + str(ch))

            # get channel names
            try:
                channels_names.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                      ['Channels']['Channel'][ch]['Name'])
            except KeyError as e:
                try:
                    channels_names.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                          ['Channels']['Channel'][ch]['@Name'])
                except KeyError as e:
                    print('Channel name not found :', e)
                    channels_names.append('CH' + str(ch))

            # get channel colors
            try:
                channels_colors.append(metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
                                       ['Channels']['Channel'][ch]['Color'])
            except KeyError as e:
                print('Channel color not found :', e)
                # use grayscale instead
                channels_colors.append('80808000')

    # write channels information (as lists) into metadata dictionary
    metadata['Channels'] = channels
    metadata['ChannelNames'] = channels_names
    metadata['ChannelColors'] = channels_colors

    try:
        metadata['SizeT'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeT'])
    except KeyError as e:
        print('No T Dimension :', e)
        if dim2none:
            metadata['SizeT'] = None
        if not dim2none:
            metadata['SizeT'] = 1

    try:
        metadata['SizeM'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeM'])
    except KeyError as e:
        print('No M Dimension :', e)
        if dim2none:
            metadata['SizeM'] = None
        if not dim2none:
            metadata['SizeM'] = 1

    try:
        metadata['SizeB'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeB'])
    except KeyError as e:
        print('No B Dimension :', e)
        if dim2none:
            metadata['SizeB'] = None
        if not dim2none:
            metadata['SizeB'] = 1

    try:
        metadata['SizeS'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeS'])
    except KeyError as e:
        print('No S Dimension :', e)
        if dim2none:
            metadata['SizeS'] = None
        if not dim2none:
            metadata['SizeS'] = 1

    try:
        metadata['SizeH'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeH'])
    except KeyError as e:
        print('No H Dimension :', e)
        if dim2none:
            metadata['SizeH'] = None
        if not dim2none:
            metadata['SizeH'] = 1

    try:
        metadata['SizeI'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeI'])
    except KeyError as e:
        print('No I Dimension :', e)
        if dim2none:
            metadata['SizeI'] = None
        if not dim2none:
            metadata['SizeI'] = 1

    try:
        metadata['SizeV'] = np.int(metadatadict_czi['ImageDocument']['Metadata']['Information']['Image']['SizeV'])
    except KeyError as e:
        print('No V Dimension :', e)
        if dim2none:
            metadata['SizeV'] = None
        if not dim2none:
            metadata['SizeV'] = 1

    # get the XY scaling information
    try:
        metadata['XScale'] = float(metadatadict_czi['ImageDocument']['Metadata']['Scaling']['Items']['Distance'][0]['Value']) * 1000000
        metadata['YScale'] = float(metadatadict_czi['ImageDocument']['Metadata']['Scaling']['Items']['Distance'][1]['Value']) * 1000000
        metadata['XScale'] = np.round(metadata['XScale'], 3)
        metadata['YScale'] = np.round(metadata['YScale'], 3)
        try:
            metadata['XScaleUnit'] = metadatadict_czi['ImageDocument']['Metadata']['Scaling']['Items']['Distance'][0]['DefaultUnitFormat']
            metadata['YScaleUnit'] = metadatadict_czi['ImageDocument']['Metadata']['Scaling']['Items']['Distance'][1]['DefaultUnitFormat']
        except (KeyError, TypeError) as e:
            print('Error extracting XY ScaleUnit :', e)
            metadata['XScaleUnit'] = None
            metadata['YScaleUnit'] = None
    except (KeyError, TypeError) as e:
        print('Error extracting XY Scale  :', e)

    # get the Z scaling information
    try:
        metadata['ZScale'] = float(metadatadict_czi['ImageDocument']['Metadata']['Scaling']['Items']['Distance'][2]['Value']) * 1000000
        metadata['ZScale'] = np.round(metadata['ZScale'], 3)
        # additional check for faulty z-scaling
        if metadata['ZScale'] == 0.0:
            metadata['ZScale'] = 1.0
        try:
            metadata['ZScaleUnit'] = metadatadict_czi['ImageDocument']['Metadata']['Scaling']['Items']['Distance'][2]['DefaultUnitFormat']
        except (IndexError, KeyError, TypeError) as e:
            print('Error extracting Z ScaleUnit :', e)
            metadata['ZScaleUnit'] = metadata['XScaleUnit']
    except (IndexError, KeyError, TypeError) as e:
        print('Error extracting Z Scale  :', e)
        if dim2none:
            metadata['ZScale'] = None
            metadata['ZScaleUnit'] = None
        if not dim2none:
            # set to isotropic scaling if it was single plane only
            metadata['ZScale'] = metadata['XScale']
            metadata['ZScaleUnit'] = metadata['XScaleUnit']

    # convert scale unit to avoid encoding problems
    if convert_scunit:
        if metadata['XScaleUnit'] == 'µm':
            metadata['XScaleUnit'] = 'micron'
        if metadata['YScaleUnit'] == 'µm':
            metadata['YScaleUnit'] = 'micron'
        if metadata['ZScaleUnit'] == 'µm':
            metadata['ZScaleUnit'] = 'micron'

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

    # check if Instrument metadat actually exist
    if pydash.objects.has(metadatadict_czi, ['ImageDocument', 'Metadata', 'Information', 'Instrument']):
        if metadatadict_czi['ImageDocument']['Metadata']['Information']['Instrument'] is not None:
            # get objective data
            if isinstance(metadatadict_czi['ImageDocument']['Metadata']['Information']['Instrument']['Objectives']['Objective'], list):
                num_obj = len(metadatadict_czi['ImageDocument']['Metadata']['Information']['Instrument']['Objectives']['Objective'])
            else:
                num_obj = 1

            # if there is only one objective found
            if num_obj == 1:
                try:
                    metadata['ObjName'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                               ['Instrument']['Objectives']['Objective']['Name'])
                except (KeyError, TypeError) as e:
                    print('No Objective Name :', e)
                    metadata['ObjName'].append(None)

                try:
                    metadata['ObjImmersion'] = metadatadict_czi['ImageDocument']['Metadata']['Information']['Instrument']['Objectives']['Objective']['Immersion']
                except (KeyError, TypeError) as e:
                    print('No Objective Immersion :', e)
                    metadata['ObjImmersion'] = None

                try:
                    metadata['ObjNA'] = np.float(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                 ['Instrument']['Objectives']['Objective']['LensNA'])
                except (KeyError, TypeError) as e:
                    print('No Objective NA :', e)
                    metadata['ObjNA'] = None

                try:
                    metadata['ObjID'] = metadatadict_czi['ImageDocument']['Metadata']['Information']['Instrument']['Objectives']['Objective']['Id']
                except (KeyError, TypeError) as e:
                    print('No Objective ID :', e)
                    metadata['ObjID'] = None

                try:
                    metadata['TubelensMag'] = np.float(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                       ['Instrument']['TubeLenses']['TubeLens']['Magnification'])
                except (KeyError, TypeError) as e:
                    print('No Tubelens Mag. :', e, 'Using Default Value = 1.0.')
                    metadata['TubelensMag'] = 1.0

                try:
                    metadata['ObjNominalMag'] = np.float(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                         ['Instrument']['Objectives']['Objective']['NominalMagnification'])
                except (KeyError, TypeError) as e:
                    print('No Nominal Mag.:', e, 'Using Default Value = 1.0.')
                    metadata['ObjNominalMag'] = 1.0

                try:
                    if metadata['TubelensMag'] is not None:
                        metadata['ObjMag'] = metadata['ObjNominalMag'] * metadata['TubelensMag']
                    if metadata['TubelensMag'] is None:
                        print('Using Tublens Mag = 1.0 for calculating Objective Magnification.')
                        metadata['ObjMag'] = metadata['ObjNominalMag'] * 1.0

                except (KeyError, TypeError) as e:
                    print('No Objective Magnification :', e)
                    metadata['ObjMag'] = None

            if num_obj > 1:
                for o in range(num_obj):

                    try:
                        metadata['ObjName'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                   ['Instrument']['Objectives']['Objective'][o]['Name'])
                    except KeyError as e:
                        print('No Objective Name :', e)
                        metadata['ObjName'].append(None)

                    try:
                        metadata['ObjImmersion'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                        ['Instrument']['Objectives']['Objective'][o]['Immersion'])
                    except KeyError as e:
                        print('No Objective Immersion :', e)
                        metadata['ObjImmersion'].append(None)

                    try:
                        metadata['ObjNA'].append(np.float(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                          ['Instrument']['Objectives']['Objective'][o]['LensNA']))
                    except KeyError as e:
                        print('No Objective NA :', e)
                        metadata['ObjNA'].append(None)

                    try:
                        metadata['ObjID'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                 ['Instrument']['Objectives']['Objective'][o]['Id'])
                    except KeyError as e:
                        print('No Objective ID :', e)
                        metadata['ObjID'].append(None)

                    try:
                        metadata['TubelensMag'].append(np.float(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                                ['Instrument']['TubeLenses']['TubeLens'][o]['Magnification']))
                    except KeyError as e:
                        print('No Tubelens Mag. :', e, 'Using Default Value = 1.0.')
                        metadata['TubelensMag'].append(1.0)

                    try:
                        metadata['ObjNominalMag'].append(np.float(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                                  ['Instrument']['Objectives']['Objective'][o]['NominalMagnification']))
                    except KeyError as e:
                        print('No Nominal Mag. :', e, 'Using Default Value = 1.0.')
                        metadata['ObjNominalMag'].append(1.0)

                    try:
                        if metadata['TubelensMag'] is not None:
                            metadata['ObjMag'].append(metadata['ObjNominalMag'][o] * metadata['TubelensMag'][o])
                        if metadata['TubelensMag'] is None:
                            print('Using Tublens Mag = 1.0 for calculating Objective Magnification.')
                            metadata['ObjMag'].append(metadata['ObjNominalMag'][o] * 1.0)

                    except KeyError as e:
                        print('No Objective Magnification :', e)
                        metadata['ObjMag'].append(None)

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
                print('DetectorID not found :', e)
                metadata['DetectorID'].append(None)

            # check for detector Name
            try:
                metadata['DetectorName'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                ['Instrument']['Detectors']['Detector']['Name'])
            except KeyError as e:
                print('DetectorName not found :', e)
                metadata['DetectorName'].append(None)

            # check for detector model
            try:
                metadata['DetectorModel'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                 ['Instrument']['Detectors']['Detector']['Manufacturer']['Model'])
            except KeyError as e:
                print('DetectorModel not found :', e)
                metadata['DetectorModel'].append(None)

            # check for detector type
            try:
                metadata['DetectorType'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                ['Instrument']['Detectors']['Detector']['Type'])
            except KeyError as e:
                print('DetectorType not found :', e)
                metadata['DetectorType'].append(None)

        if num_detectors > 1:
            for d in range(num_detectors):

                # check for detector ID
                try:
                    metadata['DetectorID'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                  ['Instrument']['Detectors']['Detector'][d]['Id'])
                except KeyError as e:
                    print('DetectorID not found :', e)
                    metadata['DetectorID'].append(None)

                # check for detector Name
                try:
                    metadata['DetectorName'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                    ['Instrument']['Detectors']['Detector'][d]['Name'])
                except KeyError as e:
                    print('DetectorName not found :', e)
                    metadata['DetectorName'].append(None)

                # check for detector model
                try:
                    metadata['DetectorModel'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                     ['Instrument']['Detectors']['Detector'][d]['Manufacturer']['Model'])
                except KeyError as e:
                    print('DetectorModel not found :', e)
                    metadata['DetectorModel'].append(None)

                # check for detector type
                try:
                    metadata['DetectorType'].append(metadatadict_czi['ImageDocument']['Metadata']['Information']
                                                    ['Instrument']['Detectors']['Detector'][d]['Type'])
                except KeyError as e:
                    print('DetectorType not found :', e)
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
                    print('WellArray Names not found :', e)
                    try:
                        metadata['Well_ArrayNames'].append(well['Name'])
                    except KeyError as e:
                        print('Well Name not found :', e, 'Using A1 instead')
                        metadata['Well_ArrayNames'].append('A1')

                try:
                    metadata['Well_Indices'].append(allscenes['Index'])
                except KeyError as e:
                    try:
                        metadata['Well_Indices'].append(allscenes['@Index'])
                    except KeyError as e:
                        print('Well Index not found :', e)
                        metadata['Well_Indices'].append(1)

                try:
                    metadata['Well_PositionNames'].append(allscenes['Name'])
                except KeyError as e:
                    try:
                        metadata['Well_PositionNames'].append(allscenes['@Name'])
                    except KeyError as e:
                        print('Well Position Names not found :', e)
                        metadata['Well_PositionNames'].append('P1')

                try:
                    metadata['Well_ColId'].append(np.int(allscenes['Shape']['ColumnIndex']))
                except KeyError as e:
                    print('Well ColumnIDs not found :', e)
                    metadata['Well_ColId'].append(0)

                try:
                    metadata['Well_RowId'].append(np.int(allscenes['Shape']['RowIndex']))
                except KeyError as e:
                    print('Well RowIDs not found :', e)
                    metadata['Well_RowId'].append(0)

                try:
                    # count the content of the list, e.g. how many time a certain well was detected
                    metadata['WellCounter'] = Counter(metadata['Well_ArrayNames'])
                except KeyError:
                    metadata['WellCounter'].append(Counter({'A1': 1}))

                try:
                    # get the SceneCenter Position
                    sx = allscenes['CenterPosition'].split(',')[0]
                    sy = allscenes['CenterPosition'].split(',')[1]
                    metadata['SceneStageCenterX'].append(np.double(sx))
                    metadata['SceneStageCenterY'].append(np.double(sy))
                except (TypeError, KeyError) as e:
                    print('Stage Positions XY not found :', e)
                    metadata['SceneStageCenterX'].append(0.0)
                    metadata['SceneStageCenterY'].append(0.0)

            if metadata['SizeS'] > 1:
                try:
                    well = allscenes[s]
                    metadata['Well_ArrayNames'].append(well['ArrayName'])
                except KeyError as e:
                    print('Well ArrayNames not found :', e)
                    try:
                        metadata['Well_ArrayNames'].append(well['Name'])
                    except KeyError as e:
                        print('Well Name not found :', e, 'Using A1 instead')
                        metadata['Well_ArrayNames'].append('A1')

                # get the well information
                try:
                    metadata['Well_Indices'].append(well['Index'])
                except KeyError as e:
                    try:
                        metadata['Well_Indices'].append(well['@Index'])
                    except KeyError as e:
                        print('Well Index not found :', e)
                        metadata['Well_Indices'].append(None)
                try:
                    metadata['Well_PositionNames'].append(well['Name'])
                except KeyError as e:
                    try:
                        metadata['Well_PositionNames'].append(well['@Name'])
                    except KeyError as e:
                        print('Well Position Names not found :', e)
                        metadata['Well_PositionNames'].append(None)

                try:
                    metadata['Well_ColId'].append(np.int(well['Shape']['ColumnIndex']))
                except KeyError as e:
                    print('Well ColumnIDs not found :', e)
                    metadata['Well_ColId'].append(None)

                try:
                    metadata['Well_RowId'].append(np.int(well['Shape']['RowIndex']))
                except KeyError as e:
                    print('Well RowIDs not found :', e)
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
                        print('Stage Positions XY not found :', e)
                        metadata['SceneCenterX'].append(0.0)
                        metadata['SceneCenterY'].append(0.0)
                if not isinstance(allscenes, list):
                    metadata['SceneStageCenterX'].append(0.0)
                    metadata['SceneStageCenterY'].append(0.0)

            # count the number of different wells
            metadata['NumWells'] = len(metadata['WellCounter'].keys())

    except (KeyError, TypeError) as e:
        print('No valid Scene or Well information found:', e)

    # get the dimensions of the bounding boxes for the scenes
    #metadata['BBoxes_Scenes'] = getbboxes_allscenes(czi, metadata, numscenes=metadata['SizeS'])

    metadata['bbox_all_scenes'] = czi.get_all_scene_bounding_boxes()
    if czi.is_mosaic():
        metadata['bbox_all_mosaic_scenes'] = czi.get_all_mosaic_scene_bounding_boxes()
        metadata['bbox_all_mosaic_tiles'] = czi.get_all_mosaic_tile_bounding_boxes()
        metadata['bbox_all_tiles'] = czi.get_all_tile_bounding_boxes()

    # get additional meta data about the experiment etc.
    metadata_add = get_additional_metadata_czi(metadatadict_czi)

    return metadata, metadata_add


def get_additional_metadata_czi(metadatadict_czi):
    """
    Returns a dictionary with additional CZI metadata.

    :param metadatadict_czi: complete metadata dictionary of the CZI image
    :type metadatadict_czi: dict
    :return: additional_czimd - dictionary with additional CZI metadata
    :rtype: dict
    """

    additional_czimd = {}

    try:
        additional_czimd['Experiment'] = metadatadict_czi['ImageDocument']['Metadata']['Experiment']
    except KeyError as e:
        print('Key not found :', e)
        additional_czimd['Experiment'] = None

    try:
        additional_czimd['HardwareSetting'] = metadatadict_czi['ImageDocument']['Metadata']['HardwareSetting']
    except KeyError as e:
        print('Key not found :', e)
        additional_czimd['HardwareSetting'] = None

    try:
        additional_czimd['CustomAttributes'] = metadatadict_czi['ImageDocument']['Metadata']['CustomAttributes']
    except KeyError as e:
        print('Key not found :', e)
        additional_czimd['CustomAttributes'] = None

    try:
        additional_czimd['DisplaySetting'] = metadatadict_czi['ImageDocument']['Metadata']['DisplaySetting']
    except KeyError as e:
        print('Key not found :', e)
        additional_czimd['DisplaySetting'] = None

    try:
        additional_czimd['Layers'] = metadatadict_czi['ImageDocument']['Metadata']['Layers']
    except KeyError as e:
        print('Key not found :', e)
        additional_czimd['Layers'] = None

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
    except (KeyError, TypeError) as e:
        print(e, 'Using defaults = 1.0')

    return scalefactors


def check_for_previewimage(czi):
    """Check if the CZI contains an image from a prescan camera

    :param czi: CZI imagefile object (using czifile)
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


def update5dstack(image5d, image2d,
                  dimstring5d='TCZYX',
                  t=0,
                  z=0,
                  c=0):

    # remove XY dimenson string
    dimstring5d = dimstring5d.replace('X', '').replace('Y', '')

    if dimstring5d == 'TZC':
        image5d[t, z, c, :, :] = image2d
    if dimstring5d == 'TCZ':
        image5d[t, c, z, :, :] = image2d
    if dimstring5d == 'ZTC':
        image5d[z, t, c, :, :] = image2d
    if dimstring5d == 'ZCT':
        image5d[z, c, t, :, :] = image2d
    if dimstring5d == 'CTZ':
        image5d[c, t, z, :, :] = image2d
    if dimstring5d == 'CZT':
        image5d[c, z, t, :, :] = image2d

    return image5d


def getdims_pylibczi(czi):

    # Get the shape of the data, the coordinate pairs are (start index, size)
    # [{'X': (0, 1900), 'Y': (0, 1300), 'Z': (0, 60), 'C': (0, 4), 'S': (0, 40), 'B': (0, 1)}]
    # dimensions = czi.dims_shape()

    dimsizes = {}
    for d in range(len(czi.dims)):
        # print(d)
        dimsizes['Size' + czi.dims[d]] = czi.size[d]

    return dimsizes


# function to return key for any value
def get_key(my_dict, val):
    """Get the key based on a value

    :param my_dict: dictionary with key - value pair
    :type my_dict: [dict
    :param val: value used to find the key
    :type val: any
    :return: key
    :rtype: any
    """
    for key, value in my_dict.items():
        if val == value:
            return key

    return None


def expand_dims5d(array, metadata):

    # Expand image array to 5D of order (T, Z, C, X, Y)
    if metadata['SizeC'] == 1:
        array = np.expand_dims(array, axis=-3)
    if metadata['SizeZ'] == 1:
        array = np.expand_dims(array, axis=-4)
    if metadata['SizeT'] == 1:
        array = np.expand_dims(array, axis=-5)

    return array


def define_czi_planetable():
    """Define the columns for the dataframe containing the planetable for a CZI image

    :return: empty dataframe with predefined columns
    :rtype: pandas.DataFrame
    """
    df = pd.DataFrame(columns=['Subblock',
                               'Scene',
                               'Tile',
                               'T',
                               'Z',
                               'C',
                               'X[micron]',
                               'Y[micron]',
                               'Z[micron]',
                               'Time[s]',
                               'xstart',
                               'ystart',
                               'xwidth',
                               'ywidth'])

    return df


def get_czi_planetable(czifile):

    # get the czi object using pylibczi
    czi = aicspylibczi.CziFile(czifile)

    # get the czi metadata
    md, add = imf.get_metadata(czifile)

    # initialize the plane table
    df_czi = define_czi_planetable()

    # define subblock counter
    sbcount = -1

    # create progressbar
    # total = md['SizeS'] * md['SizeM'] * md['SizeT'] * md['SizeZ'] * md['SizeC']
    # pbar = tqdm(total=total)

    # pbar = progressbar.ProgressBar(max_value=total)
    # in case the CZI has the M-Dimension
    if md['czi_isMosaic']:

        for s, m, t, z, c in product(range(md['SizeS']),
                                     range(md['SizeM']),
                                     range(md['SizeT']),
                                     range(md['SizeZ']),
                                     range(md['SizeC'])):

            sbcount += 1
            # print(s, m, t, z, c)
            info = czi.read_subblock_rect(S=s, M=m, T=t, Z=z, C=c)

            # read information from subblock
            sb = czi.read_subblock_metadata(unified_xml=True,
                                            B=0,
                                            S=s,
                                            M=m,
                                            T=t,
                                            Z=z,
                                            C=c)

            try:
                time = sb.xpath('//AcquisitionTime')[0].text
                timestamp = dt.parse(time).timestamp()
            except IndexError as e:
                timestamp = 0.0

            try:
                xpos = np.double(sb.xpath('//StageXPosition')[0].text)
            except IndexError as e:
                xpos = 0.0

            try:
                ypos = np.double(sb.xpath('//StageYPosition')[0].text)
            except IndexError as e:
                ypos = 0.0

            try:
                zpos = np.double(sb.xpath('//FocusPosition')[0].text)
            except IndexError as e:
                zpos = 0.0

            df_czi = df_czi.append({'Subblock': sbcount,
                                    'Scene': s,
                                    'Tile': m,
                                    'T': t,
                                    'Z': z,
                                    'C': c,
                                    'X[micron]': xpos,
                                    'Y[micron]': ypos,
                                    'Z[micron]': zpos,
                                    'Time[s]': timestamp,
                                    'xstart': info[0],
                                    'ystart': info[1],
                                    'xwidth': info[2],
                                    'ywidth': info[3]},
                                   ignore_index=True)

    if not md['czi_isMosaic']:

        """
        for s, t, z, c in it.product(range(md['SizeS']),
                                     range(md['SizeT']),
                                     range(md['SizeZ']),
                                     range(md['SizeC'])):
        """

        for s, t, z, c in product(range(md['SizeS']),
                                  range(md['SizeT']),
                                  range(md['SizeZ']),
                                  range(md['SizeC'])):

            sbcount += 1
            info = czi.read_subblock_rect(S=s, T=t, Z=z, C=c)

            # read information from subblocks
            sb = czi.read_subblock_metadata(unified_xml=True, B=0, S=s, T=t, Z=z, C=c)

            try:
                time = sb.xpath('//AcquisitionTime')[0].text
                timestamp = dt.parse(time).timestamp()
            except IndexError as e:
                timestamp = 0.0

            try:
                xpos = np.double(sb.xpath('//StageXPosition')[0].text)
            except IndexError as e:
                xpos = 0.0

            try:
                ypos = np.double(sb.xpath('//StageYPosition')[0].text)
            except IndexError as e:
                ypos = 0.0

            try:
                zpos = np.double(sb.xpath('//FocusPosition')[0].text)
            except IndexError as e:
                zpos = 0.0

            df_czi = df_czi.append({'Subblock': sbcount,
                                    'Scene': s,
                                    'Tile': 0,
                                    'T': t,
                                    'Z': z,
                                    'C': c,
                                    'X[micron]': xpos,
                                    'Y[micron]': ypos,
                                    'Z[micron]': zpos,
                                    'Time[s]': timestamp,
                                    'xstart': info[0],
                                    'ystart': info[1],
                                    'xwidth': info[2],
                                    'ywidth': info[3]},
                                   ignore_index=True)

    # normalize timestamps
    df_czi = imf.norm_columns(df_czi, colname='Time[s]', mode='min')

    # cast data  types
    df_czi = df_czi.astype({'Subblock': 'int32',
                            'Scene': 'int32',
                            'Tile': 'int32',
                            'T': 'int32',
                            'Z': 'int32',
                            'C': 'int16',
                            'xstart': 'int32',
                            'xstart': 'int32',
                            'ystart': 'int32',
                            'xwidth': 'int32',
                            'ywidth': 'int32'},
                           copy=False,
                           errors='ignore')

    return df_czi


def save_planetable(df, filename, separator=',', index=True):
    """Save dataframe as CSV table

    :param df: Dataframe to be saved as CSV.
    :type df: pd.DataFrame
    :param filename: filename of the CSV to be written
    :type filename: str
    :param separator: seperator for the CSV file, defaults to ','
    :type separator: str, optional
    :param index: option write the index into the CSV file, defaults to True
    :type index: bool, optional
    :return: filename of the csvfile that was written
    :rtype: str
    """
    csvfile = os.path.splitext(filename)[0] + '_planetable.csv'

    # write the CSV data table
    df.to_csv(csvfile, sep=separator, index=index)

    return csvfile


def norm_columns(df, colname='Time [s]', mode='min'):
    """Normalize a specific column inside a Pandas dataframe

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


def filterplanetable(planetable, S=0, T=0, Z=0, C=0):

    # filter planetable for specific scene
    if S > planetable['Scene'].max():
        print('Scene Index was invalid. Using Scene = 0.')
        S = 0
    pt = planetable[planetable['Scene'] == S]

    # filter planetable for specific timepoint
    if T > planetable['T'].max():
        print('Time Index was invalid. Using T = 0.')
        T = 0
    pt = planetable[planetable['T'] == T]

    # filter resulting planetable pt for a specific z-plane
    try:
        if Z > planetable['Z[micron]'].max():
            print('Z-Plane Index was invalid. Using Z = 0.')
            zplane = 0
            pt = pt[pt['Z[micron]'] == Z]
    except KeyError as e:
        if Z > planetable['Z [micron]'].max():
            print('Z-Plane Index was invalid. Using Z = 0.')
            zplane = 0
            pt = pt[pt['Z [micron]'] == Z]

    # filter planetable for specific channel
    if C > planetable['C'].max():
        print('Channel Index was invalid. Using C = 0.')
        C = 0
    pt = planetable[planetable['C'] == C]

    # return filtered planetable
    return pt


def get_bbox_scene(cziobject, sceneindex=0):
    """Get the min / max extend of a given scene from a CZI mosaic image
    at pyramid level = 0 (full resolution)

    :param czi: CZI object for from aicspylibczi
    :type czi: Zeiss CZI file object
    :param sceneindex: index of the scene, defaults to 0
    :type sceneindex: int, optional
    :return: tuple with (XSTART, YSTART, WIDTH, HEIGHT) extend in pixels
    :rtype: tuple
    """

    # get all bounding boxes
    bboxes = cziobject.mosaic_scene_bounding_boxes(index=sceneindex)

    # initialize lists for required values
    xstart = []
    ystart = []
    tilewidth = []
    tileheight = []

    # loop over all tiles for the specified scene
    for box in bboxes:

        # get xstart, ystart amd tile widths and heights
        xstart.append(box[0])
        ystart.append(box[1])
        tilewidth.append(box[2])
        tileheight.append(box[3])

    # get bounding box for the current scene
    XSTART = min(xstart)
    YSTART = min(ystart)

    # do not forget to add the width and height of the last tile :-)
    WIDTH = max(xstart) - XSTART + tilewidth[-1]
    HEIGHT = max(ystart) - YSTART + tileheight[-1]

    return XSTART, YSTART, WIDTH, HEIGHT


def read_scene_bbox(cziobject, metadata,
                    sceneindex=0,
                    channel=0,
                    timepoint=0,
                    zplane=0,
                    scalefactor=1.0):
    """Read a specific scene from a CZI image file.

    : param cziobject: The CziFile reader object from aicspylibczi
    : type cziobject: CziFile
    : param metadata: Image metadata dictionary from imgfileutils
    : type metadata: dict
    : param sceneindex: Index of scene, defaults to 0
    : type sceneindex: int, optional
    : param channel: Index of channel, defaults to 0
    : type channel: int, optional
    : param timepoint: Index of Timepoint, defaults to 0
    : type timepoint: int, optional
    : param zplane: Index of z - plane, defaults to 0
    : type zplane: int, optional
    : param scalefactor: scaling factor to read CZI image pyramid, defaults to 1.0
    : type scalefactor: float, optional
    : return: scene as a numpy array
    : rtype: NumPy.Array
    """
    # set variables
    scene = None
    hasT = False
    hasZ = False

    # check if scalefactor has a reasonable value
    if scalefactor < 0.01 or scalefactor > 1.0:
        print('Scalefactor too small or too large. Will use 1.0 as fallback')
        scalefactor = 1.0

    # check if CZI has T or Z dimension
    if 'T' in metadata['dims_aicspylibczi']:
        hasT = True
    if 'Z' in metadata['dims_aicspylibczi']:
        hasZ = True

    # get the bounding box for the specified scene
    xmin, ymin, width, height = get_bbox_scene(cziobject,
                                               sceneindex=sceneindex)

    # read the scene as numpy array using the correct function calls
    if hasT is True and hasZ is True:
        scene = cziobject.read_mosaic(region=(xmin, ymin, width, height),
                                      scale_factor=scalefactor,
                                      T=timepoint,
                                      Z=zplane,
                                      C=channel)

    if hasT is True and hasZ is False:
        scene = cziobject.read_mosaic(region=(xmin, ymin, width, height),
                                      scale_factor=scalefactor,
                                      T=timepoint,
                                      C=channel)

    if hasT is False and hasZ is True:
        scene = cziobject.read_mosaic(region=(xmin, ymin, width, height),
                                      scale_factor=scalefactor,
                                      Z=zplane,
                                      C=channel)

    if hasT is False and hasZ is False:
        scene = cziobject.read_mosaic(region=(xmin, ymin, width, height),
                                      scale_factor=scalefactor,
                                      C=channel)

    # add new entries to metadata to adjust XY scale due to scaling factor
    metadata['XScale Pyramid'] = metadata['XScale'] * 1 / scalefactor
    metadata['YScale Pyramid'] = metadata['YScale'] * 1 / scalefactor

    return scene, (xmin, ymin, width, height), metadata


def getbboxes_allscenes(czi, md, numscenes=1):

    all_bboxes = []
    for s in range(numscenes):
        sc = CZIScene(czi, md, sceneindex=s)
        all_bboxes.append(sc)

    return all_bboxes


class CZIScene:
    def __init__(self, czi, md, sceneindex):

        if not md['isMosaic']:
            self.bbox = czi.get_all_scene_bounding_boxes()[sceneindex]
        if md['isMosaic']:
            self.bbox = czi.get_mosaic_scene_bounding_box(index=sceneindex)

        self.xstart = self.bbox.x
        self.ystart = self.bbox.y
        self.width = self.bbox.w
        self.height = self.bbox.h
        self.index = sceneindex
        self.hasT = False
        self.hasZ = False
        self.hasS = False
        self.hasM = False
        self.hasH = False
        self.hasB = False

        if 'C' in czi.dims:
            self.hasC = True
            self.sizeC = czi.get_dims_shape()[0]['C'][1]
        else:
            self.hasC = False
            self.sizeC = None

        if 'T' in czi.dims:
            self.hasT = True
            self.sizeT = czi.get_dims_shape()[0]['T'][1]
        else:
            self.hasT = False
            self.sizeT = None

        if 'Z' in czi.dims:
            self.hasZ = True
            self.sizeZ = czi.get_dims_shape()[0]['Z'][1]
        else:
            self.hasZ = False
            self.sizeZ = None

        if 'S' in czi.dims:
            self.hasS = True
            self.sizeS = czi.get_dims_shape()[0]['S'][1]
        else:
            self.hasS = False
            self.sizeS = None

        if 'M' in czi.dims:
            self.hasM = True
            self.sizeM = czi.get_dims_shape()[0]['M'][1]
        else:
            self.hasM = False
            self.sizeM = None

        if 'B' in czi.dims:
            self.hasB = True
            self.sizeB = czi.get_dims_shape()[0]['B'][1]
        else:
            self.hasB = False
            self.sizeB = None

        if 'H' in czi.dims:
            self.hasH = True
            self.sizeH = czi.get_dims_shape()[0]['H'][1]
        else:
            self.hasH = False
            self.sizeH = None

        # determine the shape of the scene
        self.shape_single_scene = []
        #self.single_scene_dimstr = 'S'
        self.single_scene_dimstr = ''

        dims_to_ignore = ['H', 'M', 'A', 'Y', 'X']

        # get the dimension identifier
        for d in czi.dims:
            if d not in dims_to_ignore:

                if d == 'S':
                    # set size of scene dimension to 1 because shape_single_scene
                    dimsize = 1
                else:
                    # get the position inside string
                    dimpos = czi.dims.index(d)
                    dimsize = czi.size[dimpos]

                # append
                self.shape_single_scene.append(dimsize)
                self.single_scene_dimstr = self.single_scene_dimstr + d

        # add X and Y size to the shape and dimstring for the specific scene
        self.shape_single_scene.append(self.height)
        self.shape_single_scene.append(self.width)
        self.single_scene_dimstr = self.single_scene_dimstr + 'YX'

        # position for dimension for scene array
        self.posC = self.single_scene_dimstr.index('C')
        try:
            self.posZ = self.single_scene_dimstr.index('Z')
        except ValueError as e:
            print('No Z-Dimension found.')
            self.posZ = None

        try:
            self.posT = self.single_scene_dimstr.index('T')
        except ValueError as e:
            print('No T-Dimension found.')
            self.posT = None


def get_shape_allscenes(czi, md):

    shape_single_scenes = []

    # loop over all scenes
    for s in range(md['SizeS']):

        # get info for a single scene
        single_scene = CZIScene(czi, md, s)

        # add shape info to the list for shape of all single scenes
        print('Adding shape for scene: ', s)
        shape_single_scenes.append(single_scene.shape_single_scene)

    # check if all calculated scene sizes have the same shape
    same_shape = all(elem == shape_single_scenes[0] for elem in shape_single_scenes)

    # create required array shape in case all scenes are equal
    array_size_all_scenes = None
    if same_shape:
        array_size_all_scenes = shape_single_scenes[0].copy()
        array_size_all_scenes[0] = md['SizeS']

    return array_size_all_scenes, shape_single_scenes, same_shape


def read_czi_scene(czi, scene, metadata,
                   scalefactor=1.0,
                   array_type='zarr'):

    if array_type == 'numpy':
        # create the required array for this scene as numoy array
        scene_array = np.empty(scene.shape_single_scene,
                               dtype=metadata['NumPy.dtype'])

    if array_type == "zarr":
        # create the required array for this scene as numoy array
        scene_array = zarr.create(tuple(scene.shape_single_scene),
                                  dtype=metadata['NumPy.dtype'],
                                  chunks=True)

    # check if scalefactor has a reasonable value
    if scalefactor < 0.01 or scalefactor > 1.0:
        print('Scalefactor too small or too large. Will use 1.0 as fallback')
        scalefactor = 1.0

    # read the scene as numpy array using the correct function calls
    # unfortunately a CZI not always has all dimensions.

    # in case T and Z dimension are found
    if scene.hasT is True and scene.hasZ is True:

        # create an array for the scene
        for t, z, c in it.product(range(scene.sizeT),
                                  range(scene.sizeZ),
                                  range(scene.sizeC)):

            scene_array_tzc = czi.read_mosaic(region=(scene.xstart,
                                                      scene.ystart,
                                                      scene.width,
                                                      scene.height),
                                              scale_factor=scalefactor,
                                              T=t,
                                              Z=z,
                                              C=c)

            index_list = [0] * (len(scene_array.shape) - 2)
            index_list[scene.posC] = c
            index_list[scene.posZ] = z
            index_list[scene.posT] = t
            scene_array[tuple(index_list)] = scene_array_tzc[0, 0, 0, :, :]

            # if scene.posT == 1:
            #     if scene.posZ == 2:
            #         # STZCYX
            #         #scene_array[:, t, z, c, :, :] = scene_array_tzc
            #         #scene_array[:, t, z, c, :, :] = scene_array_tzc[:, 0, 0]
            #         scene_array[0, t, z, c, :, :] = scene_array_tzc[0, 0, 0, :, :]
            #     if scene.posZ == 3:
            #         # STCZYX
            #         #scene_array[:, t, c, z, :, :] = scene_array_tzc
            #         #scene_array[:, t, c, z, :, :] = scene_array_tzc[:, 0, 0]
            #         scene_array[0, t, c, z, :, :] = scene_array_tzc[0, 0, 0, :, :]

    # in case no T and Z dimension are found
    if scene.hasT is False and scene.hasZ is False:

        # create an array for the scene
        # for c in range(czi.dims_shape()[0]['C'][1]):
        for c in range(scene.sizeC):

            scene_array_c = czi.read_mosaic(region=(scene.xstart,
                                                    scene.ystart,
                                                    scene.width,
                                                    scene.height),
                                            scale_factor=scalefactor,
                                            C=c)

            index_list = [0] * (len(scene_array.shape) - 2)
            index_list[scene.posC] = c
            scene_array[tuple(index_list)] = scene_array_c[0, :, :]

            # if scene.posC == 1:
            #     # SCTZYX
            #     #scene_array[:, c, 0, 0, :, :] = scene_array_c
            #     scene_array[0, c, 0, 0, :, :] = scene_array_c[0, :, :]
            # if scene.posC == 2:
            #     # STCZYX
            #     #scene_array[:, 0, c, 0, :, :] = scene_array_c
            #     index_list = [0] * (len(scene_array.shape) - 2)
            #     index_list[scene.posC] = c
            #     #slice_object[scene.posZ] = z
            #     scene_array[tuple(index_list)] = scene_array_c[0, :, :]
            #     #scene_array[0, 0, c, 0, :, :] = scene_array_c[0, :, :]
            # if scene.posC == 3:
            #     # STZCYX
            #     #scene_array[:, 0, 0, c, :, :] = scene_array_c
            #     scene_array[0, 0, 0, c, :, :] = scene_array_c[0, :, :]

            # if scene.posC == 1:
            #    # SCTZYX
            #    scene_array[:, c, 0:1, 0:1, ...] = scene_array_c
            # if scene.posC == 2:
            #    # STCZYX
            #    scene_array[:, 0:1, c, 0:1, ...] = scene_array_c
            # if scene.posC == 3:
            #    # STZCYX
            #    scene_array[:, 0:1, 0:1, c, ...] = scene_array_c

    if scene.hasT is False and scene.hasZ is True:

        # create an array for the scene
        for z, c in it.product(range(scene.sizeZ),
                               range(scene.sizeC)):

            scene_array_zc = czi.read_mosaic(region=(scene.xstart,
                                                     scene.ystart,
                                                     scene.width,
                                                     scene.height),
                                             scale_factor=scalefactor,
                                             Z=z,
                                             C=c)

            index_list = [0] * (len(scene_array.shape) - 2)
            index_list[scene.posC] = c
            index_list[scene.posZ] = z
            scene_array[tuple(index_list)] = scene_array_c[0, 0, :, :]

            # if scene.posC == 1:
            #     if scene.posZ == 2:
            #         # SCTZYX
            #         scene_array[0, c, 0, 0, :, :] = scene_array_zc[0, 0, :, :]
            #
            # if scene.posC == 2:
            #     if scene.posZ == 1:
            #         # SZCTYX
            #         scene_array[0, z, c, 0, :, :] = scene_array_zc[0, 0, :, :]
            #     if scene.posZ == 3:
            #         # STCZYX
            #         scene_array[0, 0, c, z, :, :] = scene_array_zc[0, 0, :, :]
            #
            # if scene.posC == 3:
            #     if scene.posZ == 2:
            #         # STZCYX
            #         scene_array[0, 0, z, c, :, :] = scene_array_zc[0, 0, :, :]

    return scene_array


def get_dtype_fromstring(pixeltype):

    dytpe = None

    if pixeltype == 'gray16' or pixeltype == 'Gray16':
        dtype = np.dtype(np.int16)
    if pixeltype == 'gray8' or pixeltype == 'Gray8':
        dtype = np.dtype(np.int8)
    if pixeltype == 'bgr48' or pixeltype == 'Bgr48':
        dtype = np.dtype(np.int16)
    if pixeltype == 'bgr24' or pixeltype == 'Bgr24':
        dtype = np.dtype(np.int8)

    return dtype


def checkdims_czi(czi, metadata):

    if 'C' in czi.dims:
        metadata['hasC'] = True
    else:
        metadata['hasC'] = False

    if 'T' in czi.dims:
        metadata['hasT'] = True
    else:
        metadata['hasT'] = False

    if 'Z' in czi.dims:
        metadata['hasZ'] = True
    else:
        metadata['hasZ'] = False

    if 'S' in czi.dims:
        metadata['hasS'] = True
    else:
        metadata['hasS'] = False

    if 'M' in czi.dims:
        metadata['hasM'] = True
    else:
        metadata['hasM'] = False

    if 'B' in czi.dims:
        metadata['hasB'] = True
    else:
        metadata['hasB'] = False

    if 'H' in czi.dims:
        metadata['hasH'] = True
    else:
        metadata['hasH'] = False

    return metadata
