# -*- coding: utf-8 -*-

#################################################################
# File        : napari_browser_cz.py
# Version     : 0.0.2
# Author      : czsrh
# Date        : 04.12.2020
# Institution : Carl Zeiss Microscopy GmbH
#
# Disclaimer: This tool is purely experimental. Feel free to
# use it at your own risk.
#
# Copyright (c) 2020 Carl Zeiss AG, Germany. All Rights Reserved.
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
    QAbstractItemView

)
from PyQt5.QtCore import Qt, QDir, QSortFilterProxyModel
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import QFont

import napari
import numpy as np
import md_tools as imf
from aicsimageio import AICSImage
import dask.array as da
import os


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

        windowLayout = QHBoxLayout()
        windowLayout.addWidget(self.tree)
        self.setLayout(windowLayout)

        self.tree.clicked.connect(self.on_treeView_clicked)

    def on_treeView_clicked(self, index):
        indexItem = self.model.index(index.row(), 0, index.parent())
        fileName = self.model.fileName(indexItem)
        filePath = self.model.filePath(indexItem)

        print('Opening ImageFile : ', filePath)
        open_image_stack(filePath)


class CheckBoxWidget(QWidget):

    def __init__(self):
        super(QWidget, self).__init__()
        self.layout = QHBoxLayout(self)
        self.cbox = QCheckBox("Use AICSImageIO Dask Delayed Reader", self)
        self.layout.addWidget(self.cbox)
        self.cbox.setChecked(True)

        # adjust font
        fnt = QFont()
        fnt.setPointSize(9)
        fnt.setBold(True)
        fnt.setFamily("Arial")
        self.cbox.setFont(fnt)


class Open_files(QWidget):

    def __init__(self):
        super(QWidget, self).__init__()
        self.layout = QHBoxLayout(self)
        self.file_dialog = QFileDialog()
        self.file_dialog.setWindowFlags(Qt.Widget)
        self.file_dialog.setModal(False)
        self.file_dialog.setOption(QFileDialog.DontUseNativeDialog)

        # remove open and cancel button from widget
        self.buttonBox = self.file_dialog.findChild(QDialogButtonBox, "buttonBox")
        self.buttonBox.clear()

        #btn = self.buttonBox.button(QDialogButtonBox.Cancel)
        # btn.setEnabled(False)
        # btn.setVisible(False)

        # only open following file types
        self.file_dialog.setNameFilter("Images (*.czi *.ome.tiff *ome.tif *.tiff *.tif)")
        self.layout.addWidget(self.file_dialog)
        # self.file_dialog.
        self.file_dialog.currentChanged.connect(open_image_stack)


def open_image_stack(path):
    """ function to open a file using AICSImageIO and display it using Napari

    :param path: filepath of the image
    :type path: str
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
        stack = img.get_image_data()

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
    :param blending: NapariViewer option for blending, defaults to 'additive'
    :type blending: str, optional
    :param gamma: NapariViewer value for Gamma, defaults to 0.85
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
            sliders = viewer.dims.axis_labels

            # update the labels with the correct dimension strings
            slidernames = ['B', 'S', 'T', 'Z']

        for s in slidernames:
            if dimpos_viewer[s] >= 0:
                sliders[dimpos_viewer[s]] = s

        # apply the new labels to the viewer
        viewer.dims.axis_labels = sliders


# start the main application
with napari.gui_qt():

    # define the parent directory
    # when using the FileTree one cannot navigate to higher levels from there
    workdir = r'C:\Users\m1srh\OneDrive - Carl Zeiss AG\Testdata_Zeiss'
    print('Working Directory : ', workdir)

    # create the classes
    #filebrowser = Open_files()
    filetree = FileTree(workdir)
    mdbrowser = TableWidget()
    checkbox = CheckBoxWidget()

    # create a viewer
    viewer = napari.Viewer()

    # add a FileTree widget
    viewer.window.add_dock_widget(filetree, name='filebrowser', area='right')

    # or add a FileDialogg widget
    #viewer.window.add_dock_widget(filebrowser, name='filebrowser', area='right')

    # add widget
    viewer.window.add_dock_widget(checkbox, name='checkbox', area='right')

    # add the Table widget for the metadata
    viewer.window.add_dock_widget(mdbrowser, name='mdbrowser', area='right')
