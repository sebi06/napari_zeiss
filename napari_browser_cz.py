# -*- coding: utf-8 -*-

#################################################################
# File        : napari_browser_cz.py
# Version     : 0.0.4
# Author      : czsrh
# Date        : 16.01.2020
# Institution : Carl Zeiss Microscopy GmbH
#
# Disclaimer: This tool is purely experimental. Feel free to
# use it at your own risk.
#
# Copyright (c) 2020 Carl Zeiss AG, Germany. All Rights Reserved.
#
#################################################################

from PyQt5.QtWidgets import (

    QHBoxLayout,
    QVBoxLayout,
    QFileSystemModel,
    QFileDialog,
    QTreeView,
    QDialogButtonBox,
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QCheckBox,
    QAbstractItemView,
    QComboBox,
    QPushButton,
    QLineEdit,
    QLabel,
    QGridLayout

)

from PyQt5.QtCore import Qt, QDir, QSortFilterProxyModel
from PyQt5.QtCore import pyqtSlot
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import QFont

import napari
import numpy as np
import md_tools as imf
from aicsimageio import AICSImage
import dask.array as da
import os
from zencontrol import ZenExperiment, ZenDocuments


class TableWidget(QWidget):

    def __init__(self):
        super(QWidget, self).__init__()
        self.layout = QVBoxLayout(self)
        self.mdtable = QTableWidget()
        self.layout.addWidget(self.mdtable)
        self.mdtable.setShowGrid(True)
        self.mdtable.setHorizontalHeaderLabels(['Parameter', 'Value'])
        header = self.mdtable.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft)

    def update_metadata(self, metadata):

        row_count = len(metadata)
        col_count = 2
        self.mdtable.setColumnCount(col_count)
        self.mdtable.setRowCount(row_count)

        row = 0

        for key, value in metadata.items():
            newkey = QTableWidgetItem(key)
            self.mdtable.setItem(row, 0, newkey)
            newvalue = QTableWidgetItem(str(value))
            self.mdtable.setItem(row, 1, newvalue)
            row += 1

        # fit columns to content
        self.mdtable.resizeColumnsToContents()

    def update_style(self):

        # define font
        fnt = QFont()
        fnt.setPointSize(11)
        fnt.setBold(True)
        fnt.setFamily('Arial')

        # update both header items
        item1 = QtWidgets.QTableWidgetItem('Parameter')
        item1.setForeground(QtGui.QColor(25, 25, 25))
        item1.setFont(fnt)
        self.mdtable.setHorizontalHeaderItem(0, item1)

        item2 = QtWidgets.QTableWidgetItem('Value')
        item2.setForeground(QtGui.QColor(25, 25, 25))
        item2.setFont(fnt)
        self.mdtable.setHorizontalHeaderItem(1, item2)


class FileTree(QWidget):

    def __init__(self, workdir):
        super(QWidget, self).__init__()

        filter = ['*.czi', '*.ome.tiff', '*ome.tif' '*.tiff' '*.tif']

        self.setStyleSheet("""
            QTreeView::item {
            background-color: rgb(38, 41, 48);
            font-weight: bold;
            }

            QTreeView::item::selected {
            background-color: rgb(38, 41, 48);
            color: rgb(0, 255, 0);

            }

            QTreeView QHeaderView:section {
            background-color: rgb(38, 41, 48);
            color: rgb(255, 255, 255);
            }
            """)

        self.model = QFileSystemModel()
        self.model.setRootPath(workdir)
        self.model.setFilter(QtCore.QDir.AllDirs | QDir.Files | QtCore.QDir.NoDotAndDotDot)
        self.model.setNameFilterDisables(False)
        self.model.setNameFilters(filter)

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(workdir))
        self.tree.setAnimated(True)
        self.tree.setIndentation(20)
        self.tree.setSortingEnabled(False)
        header = self.tree.header()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)

        windowLayout = QVBoxLayout()
        windowLayout.addWidget(self.tree)
        self.setLayout(windowLayout)

        self.tree.clicked.connect(self.on_treeView_clicked)

    @pyqtSlot()
    def on_treeView_clicked(self, index):
        indexItem = self.model.index(index.row(), 0, index.parent())
        fileName = self.model.fileName(indexItem)
        filePath = self.model.filePath(indexItem)

        print('Opening ImageFile : ', filePath)
        open_image_stack(filePath)


class OptionsWidget(QWidget):

    def __init__(self):
        super(QWidget, self).__init__()

        # Create a grid layout instance
        self.grid_opt = QGridLayout()
        self.grid_opt.setSpacing(10)
        self.setLayout(self.grid_opt)

        # add widgets to the grid layout
        self.cbox_dask = QCheckBox("Use AICSImageIO Dask Reader", self)
        self.cbox_dask.setChecked(True)
        self.cbox_dask.setStyleSheet("font:bold;"
                                     "font-size: 10px;"
                                     "width :14px;"
                                     "height :14px;"
                                     )
        self.grid_opt.addWidget(self.cbox_dask, 0, 0)

        self.cbox_openczi = QCheckBox("Open CZI after Experiment Execution", self)
        self.cbox_openczi.setChecked(True)
        self.cbox_openczi.setStyleSheet("font:bold;"
                                        "font-size: 10px;"
                                        "width :14px;"
                                        "height :14px;"
                                        )
        self.grid_opt.addWidget(self.cbox_openczi, 1, 0)


class FileBrowser(QWidget):

    def __init__(self, defaultfolder=r'c:\Zen_Output'):
        super(QWidget, self).__init__()
        self.layout = QHBoxLayout(self)
        self.file_dialog = QFileDialog()
        self.file_dialog.setWindowFlags(Qt.Widget)
        self.file_dialog.setModal(False)
        self.file_dialog.setOption(QFileDialog.DontUseNativeDialog)
        self.file_dialog.setDirectory(defaultfolder)

        # remove open and cancel button from widget
        self.buttonBox = self.file_dialog.findChild(QDialogButtonBox, "buttonBox")
        self.buttonBox.clear()

        # only open following file types
        self.file_dialog.setNameFilter("Images (*.czi *.ome.tiff *ome.tif *.tiff *.tif)")
        self.layout.addWidget(self.file_dialog)
        self.file_dialog.currentChanged.connect(open_image_stack)


class StartExperiment(QWidget):

    def __init__(self, default_cziname='myimage.czi'):
        super(QWidget, self).__init__()

        # Create a grid layout instance
        self.grid_exp = QGridLayout()
        self.grid_exp.setSpacing(10)
        self.setLayout(self.grid_exp)

        # add widgets to the grid layout
        self.expselect = QComboBox(self)
        self.expselect.addItems(expfiles_short)
        self.expselect.setStyleSheet("font: bold;"
                                     "font-size: 10px;"
                                     )
        self.grid_exp.addWidget(self.expselect, 0, 0)

        self.startexpbutton = QPushButton('Run Experiment')
        self.startexpbutton.setStyleSheet("font: bold;"
                                          # "background-color: red;"
                                          "font-size: 10px;"
                                          # "height: 48px;width: 120px;"
                                          )
        self.grid_exp.addWidget(self.startexpbutton, 0, 1)

        self.namelabel = QLabel(self)
        self.namelabel.setText('Save Experiment result as CZI :')
        self.namelabel.setStyleSheet("font: bold;"
                                     "font-size: 10px;"
                                     ""
                                     )
        self.grid_exp.addWidget(self.namelabel, 1, 0)

        self.nameedit = QLineEdit(self)
        self.nameedit.setText(default_cziname)
        self.nameedit.setFixedWidth(200)
        self.nameedit.setStyleSheet("font: bold;"
                                    "font-size: 10px;"
                                    )
        self.grid_exp.addWidget(self.nameedit, 1, 1)

        # Set the layout on the application's window
        self.startexpbutton.clicked.connect(self.on_click)

    @pyqtSlot()
    def on_click(self):

        # finding the content of current item in combo box
        current_exp = self.expselect.currentText()
        print('Selected ZEN Experiment : ', current_exp)

        # get the CZI name to be used
        desired_cziname = self.nameedit.text()

        # disable the button
        self.startexpbutton.setEnabled(False)
        self.startexpbutton.setText('Running ...')
        # QtCore.QApplication.processEvents()
        QtWidgets.QApplication.processEvents()

        # initialize the experiment
        czexp = ZenExperiment(experiment=current_exp,
                              savefolder=savefolder,
                              cziname=desired_cziname)

        # start the actual experiment
        self.saved_czifilepath = czexp.startexperiment()
        print('Saved CZI : ', self.saved_czifilepath)

        # enable the button again
        self.startexpbutton.setEnabled(True)
        self.startexpbutton.setText('Run Experiment')

        # not nice, but this "redraws" the button
        QtWidgets.QApplication.processEvents()

        # open the just recorded CZI image
        use_dask = checkboxes.cbox_dask.isChecked()
        print("Use Dask Reader : ", use_dask)

        if self.saved_czifilepath is not None:
            open_image_stack(self.saved_czifilepath, use_dask)


def open_image_stack(path, use_dask=False):
    """ Open a file using AICSImageIO and display it using Napari

    :param path: filepath of the image
    :type path: str
    :param use_dask: use Dask Delayed reader, defaults to False
    :type use_dask: bool, optional
    """

    if os.path.isfile(path):

        # remove existing layers from napari
        viewer.layers.select_all()
        viewer.layers.remove_selected()

        # get the metadata
        metadata, add_metadata = imf.get_metadata(path)

        # add the metadata and adapt the table display
        mdbrowser.update_metadata(metadata)
        mdbrowser.update_style()

        # get AICSImageIO object
        img = AICSImage(path)

        if not use_dask:
            stack = img.get_image_data()
        if use_dask:
            stack = img.get_image_dask_data()

        # add the image stack to the napari viewer
        show_image_napari(stack, metadata,
                          blending='additive',
                          gamma=0.85,
                          rename_sliders=True)


def show_image_napari(array, metadata,
                      blending='additive',
                      gamma=0.75,
                      rename_sliders=False):
    """Show the multidimensional array using the Napari viewer

    :param array: multidimensional NumPy.Array containing the pixeldata
    :type array: NumPy.Array
    :param metadata: dictionary with CZI or OME-TIFF metadata
    :type metadata: dict
    :param blending: Napari viewer option for blending, defaults to 'additive'
    :type blending: str, optional
    :param gamma: Napari viewer value for Gamma, defaults to 0.85
    :type gamma: float, optional
    :param rename_sliders: name slider with correct labels output, defaults to False
    :type verbose: bool, optional
    """

    # create scalefcator with all ones
    scalefactors = [1.0] * len(array.shape)
    dimpos = imf.get_dimpositions(metadata['Axes_aics'])

    # get the scalefactors from the metadata
    scalef = imf.get_scalefactor(metadata)

    # modify the tuple for the scales for napari
    scalefactors[dimpos['Z']] = scalef['zx']

    # remove C dimension from scalefactor
    scalefactors_ch = scalefactors.copy()
    del scalefactors_ch[dimpos['C']]

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
                print('Extract Channel as Dask.Array')
                channel = array.compute().take(ch, axis=dimpos['C'])

            else:
                # use normal numpy if not
                print('Extract Channel as NumPy.Array')
                channel = array.take(ch, axis=dimpos['C'])

            # actually show the image array
            print('Adding Channel  : ', chname)
            print('Shape Channel   : ', ch, channel.shape)
            print('Scaling Factors : ', scalefactors_ch)

            # get min-max values for initial scaling
            clim = imf.calc_scaling(channel,
                                    corr_min=1.0,
                                    offset_min=0,
                                    corr_max=0.85,
                                    offset_max=0)

            # add channel to napari viewer
            viewer.add_image(channel,
                             name=chname,
                             scale=scalefactors_ch,
                             contrast_limits=clim,
                             blending=blending,
                             gamma=gamma)

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

        # use dask if array is a dask.array
        if isinstance(array, da.Array):
            print('Extract Channel using Dask.Array')
            array = array.compute()

        # get min-max values for initial scaling
        clim = imf.calc_scaling(array)

        viewer.add_image(array,
                         name=chname,
                         scale=scalefactors,
                         contrast_limits=clim,
                         blending=blending,
                         gamma=gamma)

    if rename_sliders:

        print('Renaming the Sliders based on the Dimension String ....')

        if metadata['SizeC'] == 1:

            # get the position of dimension entries after removing C dimension
            dimpos_viewer = imf.get_dimpositions(metadata['Axes_aics'])

            # get the label of the sliders
            sliders = viewer.dims.axis_labels

            # update the labels with the correct dimension strings
            slidernames = ['B', 'S', 'T', 'Z', 'C']

        if metadata['SizeC'] > 1:

            new_dimstring = metadata['Axes_aics'].replace('C', '')

            # get the position of dimension entries after removing C dimension
            dimpos_viewer = imf.get_dimpositions(new_dimstring)

            # get the label of the sliders
            # for napari <= 0.4.2 this returns a list
            # and >= 0.4.3 it will return a tuple
            sliders = viewer.dims.axis_labels

            # update the labels with the correct dimension strings
            slidernames = ['B', 'S', 'T', 'Z']

        for s in slidernames:
            if dimpos_viewer[s] >= 0:
                try:
                    # this seems to work for napari <= 0.4.2
                    
                    # assign the dimension labels
                    sliders[dimpos_viewer[s]] = s
                except TypeError:
                    # this works for napari >= 0.4.3
                    
                    # convert to list()
                    tmp_sliders = list(sliders)
                    
                    # assign the dimension labels
                    tmp_sliders[dimpos_viewer[s]] = s
                    
                    # convert back to tuple
                    sliders = tuple(tmp_sliders)

        # apply the new labels to the viewer
        viewer.dims.axis_labels = sliders


def check_folder(folderpath):
    """ Check if  folder exits.

    :param folderpath: path of the folder to be checked
    :type folderpath: str
    :return: Boolean
    :rtype: str
    """
    # check if the ZEN experiment folder was found
    folder_check = os.path.isdir(folderpath)
    if folder_check is True:
        print(folderpath + " is a valid directory.")
    else:
        print(folderpath + "  is NOT a valid directory")

    return folder_check



##################################################

# make sure this location is correct
zenexpfolder = r'e:\Sebastian\Documents\Carl Zeiss\ZEN\Documents\Experiment Setups'
savefolder = r'e:\tuxedo\zen_output'

# check if the ZEN experiment folder was found
expfolder_exists = check_folder(zenexpfolder)
savefolder_exits = check_folder(savefolder)

# default for saving an CZI image fafter acquistion
default_cziname = 'myimage.czi'

# get lists with existing experiment files
expdocs = ZenDocuments()
expfiles_long, expfiles_short = expdocs.getfilenames(folder=zenexpfolder,
                                                     pattern='*.czexp')

# decide what widget to use - 'tree' or 'dialog'
fileselect = 'dialog'

###########################################################

# start the main application
with napari.gui_qt():

    # define the parent directory
    # when using the FileTree one cannot navigate to higher levels from there
    print('Working Directory : ', savefolder)

    # create a viewer
    viewer = napari.Viewer()

    if fileselect == 'tree':
        # add a FileTree widget
        filetree = FileTree(defaultfolder=savefolder)
        fbwidget = viewer.window.add_dock_widget(filetree, name='filebrowser', area='right')

    if fileselect == 'dialog':
        # add a FileDialogg widget
        filebrowser = FileBrowser(defaultfolder=savefolder)
        fbwidget = viewer.window.add_dock_widget(filebrowser, name='filebrowser', area='right')

    # create the widget elements
    mdbrowser = TableWidget()
    checkboxes = OptionsWidget()
    expselect = StartExperiment(default_cziname=default_cziname)

    # add widget to activate the dask delayed reading
    cbwidget = viewer.window.add_dock_widget(checkboxes, name='checkbox', area='bottom')

    # add the Table widget for the metadata
    mdwidget = viewer.window.add_dock_widget(mdbrowser, name='mdbrowser', area='right')

    # add the Experiment Selector widget
    expwidget = viewer.window.add_dock_widget(expselect, name='expselect', area='bottom')
