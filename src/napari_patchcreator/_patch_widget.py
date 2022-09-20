from copy import copy

import napari
import numpy as np
from magicgui.widgets import Widget, create_widget
from qtpy.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class PatchWidget(QWidget):
    def __init__(self, napari_viewer: napari.Viewer):
        super().__init__()

        self.viewer = napari_viewer
        self.setLayout(QVBoxLayout())
        self.setMinimumWidth(200)

        self.layer_chooser = self._layer_choice(
            annotation=napari.layers.Image, name="Source layer"
        )
        self.layout().addWidget(self.layer_chooser.native)

        formLayout = QFormLayout()
        self.patch_size_widget = self._create_int_spinbox(1, 1)
        formLayout.addRow("Patch Size", self.patch_size_widget)
        formLayout.minimumSize()
        widget = QWidget()
        widget.setLayout(formLayout)
        self.layout().addWidget(widget)

        self.enable_selection = QCheckBox("Enable/Disable selection")
        self.layout().addWidget(self.enable_selection)

        self.save_button = QPushButton("Save patches", self)
        self.layout().addWidget(self.save_button)
        self.save_button.clicked.connect(self._export_patches)
        self.enable_selection.stateChanged.connect(self.start_stop_selection)

    def _layer_choice(self, annotation, **kwargs) -> Widget:
        widget = create_widget(annotation=annotation, **kwargs)
        widget.reset_choices()
        self.viewer.layers.events.inserted.connect(widget.reset_choices)
        self.viewer.layers.events.removed.connect(widget.reset_choices)
        self.viewer.layers.events.changed.connect(widget.reset_choices)
        return widget

    def _create_int_spinbox(
        self,
        min_value: int = 1,
        value: int = 2,
        step: int = 1,
        visible: bool = True,
        tooltip: str = None,
    ) -> QSpinBox:
        spin_box = QSpinBox()
        spin_box.setMinimum(min_value)
        spin_box.setSingleStep(step)
        spin_box.setValue(value)
        spin_box.setVisible(visible)
        spin_box.setToolTip(tooltip)
        spin_box.setMinimumHeight(50)
        spin_box.setContentsMargins(0, 3, 0, 3)

        return spin_box

    def _export_patches(self):
        where = QFileDialog.getExistingDirectory(caption="Save patches")
        if "2dselection" in self.viewer.layers:
            selection_layer = self.viewer.layers["2dselection"]
            shapes = selection_layer.data
            patches = [
                self.slice_img_patch(
                    self.layer_chooser.value.data,
                    x,
                    ndim=len(self.layer_chooser.value.data.shape),
                )
                for x in shapes
            ]
            from PIL import Image

            for idx, patch in enumerate(patches):
                im = Image.fromarray(patch)
                im.save(str(where) + "/" + str(idx) + ".tif", format="TIFF")

    def start_stop_selection(self, state):
        """
        Function to start the selection. It creates the highlight and
        2dselection shape layers if they don't already exist.
        It adds and removes the mouse events for drawing and creating patches.

        :param state:
        :return:
        """
        if "highlight" not in self.viewer.layers:
            highlight_layer = self.viewer.add_shapes(name="highlight")
            self.viewer.add_shapes(
                name="2dselection",
                ndim=len(self.layer_chooser.value.data.shape),
            )
            self.viewer.layers.selection.select_only(highlight_layer)
        highlight_layer = self.viewer.layers["highlight"]
        if state:
            highlight_layer.mouse_move_callbacks.append(self.draw_square)
            highlight_layer.mouse_drag_callbacks.append(self.create_patch)
        else:
            try:
                highlight_layer.mouse_move_callbacks.remove(self.draw_square)
                highlight_layer.mouse_drag_callbacks.remove(self.create_patch)
            except ValueError:
                pass  # do nothing!

    def create_patch(self, layer, event):
        """
        Creates and adds a rectangle in the shapes layer called "2dselection"

        :param layer: the currently selected layer
        :param event: the event that triggered this event
        :return: None
        """
        if event.type == "mouse_press" and event.button == 1:
            cords = np.round(
                layer.world_to_data(self.viewer.cursor.position)
            ).astype(int)
            rectangle = self.create_rectangle(
                cords,
                self.patch_size_widget.value(),
                self.layer_chooser.value.data.shape,
                self.viewer.cursor.position,
            )
            selection_layer = self.viewer.layers["2dselection"]
            selection_layer.add_rectangles(
                rectangle,
                edge_width=1,
                edge_color="cyan",
                face_color="transparent",
            )

    def create_rectangle(
        self, cords, patch_size: int, img_layer_shape, cursor_pos
    ) -> np.array:
        """
        Creates a rectangle with a given patch size around the cursor position.

        :param cords: the cursor coordinates in data space
        :param patch_size: the edge length of the patch
        :param img_layer_shape: the img layer shape
        :param cursor_pos: the current cursor position in world space
        :return:
        """

        upper_left = cords - (patch_size / 2)
        upper_right = copy(upper_left)
        upper_right[1] += patch_size
        lower_right = cords + (patch_size / 2)
        lower_left = copy(lower_right)
        lower_left[1] -= patch_size
        rectangle = np.array(
            [upper_left, upper_right, lower_right, lower_left]
        )
        print(rectangle)
        rectangle = self.sanitize_rectangle(
            rectangle, img_layer_shape, patch_size - 1
        )
        print(rectangle)
        if len(img_layer_shape) == 3:
            current_slice = int(cursor_pos[0])
            rectangle = np.insert(rectangle, 0, current_slice, axis=1)
        return rectangle

    def draw_square(self, layer, event) -> None:
        """
        Draws a square around the cursor position with the
        edge lengths specified in the widget.
        The drawn square is first sanitized to be in-bound of the image.

        :param layer: a napari layer, usually an image layer
        :param event: unused
        :return:
        """
        cords = np.round(
            layer.world_to_data(self.viewer.cursor.position)
        ).astype(int)
        upper_left = cords - (self.patch_size_widget.value() / 2)
        lower_right = cords + (self.patch_size_widget.value() / 2)
        rectangle = np.array([upper_left, lower_right])
        layer.selected_data = set(range(layer.nshapes))
        layer.remove_selected()
        layer.add(
            self.sanitize_rectangle(
                rectangle,
                self.layer_chooser.value.data.shape,
                self.patch_size_widget.value() - 1,
            ),
            shape_type="rectangle",
            edge_width=1,
            edge_color="coral",
            face_color="transparent",
        )

    def sanitize_rectangle(
        self, rect: np.array, layer_shape: tuple, edge_length: int
    ) -> np.array:
        """
        Function to check each vertex of the rectangle and
        moves the vertices in-bounds of the images if
        they are out of bounds.

        :param rect: the rectangle to sanitize
        :param layer_shape: shape of the current layer
        :param edge_length: the length of the rectangles edge
        :return:
        """
        shape_array = np.array(layer_shape)
        y_dim = len(shape_array) - 2
        x_dim = len(shape_array) - 1
        if len(rect) == 2:
            rect[0] = self.sanitize_vertex(
                rect[0],
                0,
                shape_array[y_dim] - edge_length,
                0,
                shape_array[x_dim] - edge_length,
            )
            rect[1] = self.sanitize_vertex(
                rect[1],
                edge_length,
                shape_array[y_dim],
                edge_length,
                shape_array[x_dim],
            )
        if len(rect) == 4:
            rect[0] = self.sanitize_vertex(
                rect[0],
                0,
                shape_array[y_dim] - edge_length,
                0,
                shape_array[x_dim] - edge_length,
            )
            rect[1] = self.sanitize_vertex(
                rect[1],
                0,
                shape_array[y_dim] - edge_length,
                edge_length,
                shape_array[x_dim],
            )
            rect[2] = self.sanitize_vertex(
                rect[2],
                edge_length,
                shape_array[y_dim],
                edge_length,
                shape_array[x_dim],
            )
            rect[3] = self.sanitize_vertex(
                rect[3],
                edge_length,
                shape_array[y_dim],
                0,
                shape_array[x_dim] - edge_length,
            )
        return rect

    def sanitize_vertex(
        self,
        vertex: np.array,
        low_y: int,
        high_y: int,
        low_x: int,
        high_x: int,
    ) -> np.array:
        """
        Takes a single point in 2D space and makes sure that the
        values are in the allowed range and if not, sets the value
        to the smallest or highest possible value.
        It's used to draw the mouse-following square.

        :param vertex: a 2D point
        :param low_y: the lower limit for the first value
        :param high_y: the upper limit for the first value
        :param low_x: the lower limit for the second value
        :param high_x: the upper limit for the second value
        :return: the in-bounds vertex
        """
        vertex[0] = np.where(vertex[0] < low_y, low_y, vertex[0])
        vertex[0] = np.where(vertex[0] > high_y, high_y, vertex[0])
        vertex[1] = np.where(vertex[1] < low_x, low_x, vertex[1])
        vertex[1] = np.where(vertex[1] > high_x, high_x, vertex[1])
        return vertex

    def slice_img_patch(
        self, data: np.array, rectangle: np.array, ndim: int
    ) -> np.array:
        """
        :param data: the image to slice the patch from
        :param rectangle: the patch with its vertices
        :param ndim: the dimension of the image,
        changes the selected values of the rectangle.
        :return: the sliced out patch
        """
        if ndim == 3:
            ixgrid = np.ix_(
                np.arange(rectangle[0][1], rectangle[1][1], dtype=int),
                np.arange(rectangle[0][2], rectangle[2][2], dtype=int),
            )
            ixgrid = (int(rectangle[0][0]),) + ixgrid
            img = data[ixgrid]
            return img
        if ndim == 2:
            ixgrid = np.ix_(
                np.arange(rectangle[0][0], rectangle[1][0], dtype=int),
                np.arange(rectangle[0][1], rectangle[2][1], dtype=int),
            )
            img = data[ixgrid]
            return img


if __name__ == "__main__":
    # create a Viewer
    viewer = napari.Viewer()
    # add our plugin
    viewer.window.add_dock_widget(PatchWidget(viewer))
    napari.run()
