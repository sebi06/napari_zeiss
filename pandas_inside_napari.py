# taken from:
# https://forum.image.sc/t/how-to-remove-a-widget-from-napari-or-how-to-update-it/45536/8?u=sebi06


from qtpy import QtCore, QtWidgets
from qtpy.QtCore import Qt
import pandas as pd
import napari


class TableModel(QtCore.QAbstractTableModel):
    def __init__(self, data):
        super(TableModel, self).__init__()
        self._data = data

    def data(self, index, role):
        if role == Qt.DisplayRole:
            value = self._data.iloc[index.row(), index.column()]
            return str(value)

    def rowCount(self, index):
        return self._data.shape[0]

    def columnCount(self, index):
        return self._data.shape[1]

    def headerData(self, section, orientation, role):
        # section is the index of the column/row.
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return str(self._data.columns[section])

            if orientation == Qt.Vertical:
                return str(self._data.index[section])


class Table(QtWidgets.QWidget):
    def __init__(self, data):
        super().__init__()
        self.setLayout(QtWidgets.QHBoxLayout())
        self.table = QtWidgets.QTableView()
        self.model = TableModel(data)
        self.table.setModel(self.model)
        self.layout().addWidget(self.table)


with napari.gui_qt():
    df = pd.DataFrame(
        [[1, 9, 2], [1, 0, -1], [3, 5, 2], [3, 3, 2]],
        columns=['A', 'B', 'C'],
        index=['Row 1', 'Row 2', 'Row 3', 'Row 4'],
    )
    wdg = Table(df)
    v = napari.Viewer()
    dw = v.window.add_dock_widget(wdg)
    # call dw.update() after you modify the dataframe
