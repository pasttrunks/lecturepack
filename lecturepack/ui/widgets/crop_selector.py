from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap
from PySide6.QtCore import Qt, QRect, QRectF, QPointF

class CropSelector(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = None
        self.image_rect = QRect()
        
        # All rects stored as normalized QRectF (0.0 to 1.0)
        self.crop_rect = QRectF(0.0, 0.0, 1.0, 1.0)
        self.ignore_rects = [] # max 3 normalized QRectF
        
        self.draw_mode = "crop" # "crop" or "ignore"
        self.is_drawing = False
        self.start_norm_pos = None

    def set_preview_image(self, image_path):
        """Loads and sets the video preview frame."""
        self.pixmap = QPixmap(image_path)
        self.update()

    def clear_rects(self):
        self.crop_rect = QRectF(0.0, 0.0, 1.0, 1.0)
        self.ignore_rects = []
        self.update()

    def set_draw_mode(self, mode):
        # mode can be "crop" or "ignore"
        self.draw_mode = mode

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Draw background placeholder or loaded pixmap
        if self.pixmap and not self.pixmap.isNull():
            scaled = self.pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            px = (self.width() - scaled.width()) // 2
            py = (self.height() - scaled.height()) // 2
            self.image_rect = QRect(px, py, scaled.width(), scaled.height())
            painter.drawPixmap(self.image_rect, scaled)
        else:
            self.image_rect = self.rect()
            painter.fillRect(self.rect(), QColor(30, 30, 30))
            painter.setPen(QPen(QColor(150, 150, 150), 1, Qt.PenStyle.DashLine))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No video preview loaded")
            return

        # 2. Draw Crop Rectangle (Green)
        if self.crop_rect and not self.crop_rect.isEmpty():
            cr = self._to_widget_coords(self.crop_rect)
            painter.setPen(QPen(QColor(76, 175, 80), 2)) # Green
            painter.setBrush(QColor(76, 175, 80, 40)) # Semi-transparent green
            painter.drawRect(cr)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(76, 175, 80), 1))
            painter.drawText(int(cr.x() + 5), int(cr.y() + 15), "Crop Area")

        # 3. Draw Ignore Rectangles (Red)
        for i, ir_norm in enumerate(self.ignore_rects):
            if ir_norm and not ir_norm.isEmpty():
                ir = self._to_widget_coords(ir_norm)
                painter.setPen(QPen(QColor(244, 67, 54), 2)) # Red
                painter.setBrush(QColor(244, 67, 54, 40)) # Semi-transparent red
                painter.drawRect(ir)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(244, 67, 54), 1))
                painter.drawText(int(ir.x() + 5), int(ir.y() + 15), f"Ignore {i+1}")

    def mousePressEvent(self, event):
        if not self.pixmap or self.pixmap.isNull():
            return
        
        pos = event.position()
        if self.image_rect.contains(int(pos.x()), int(pos.y())):
            self.is_drawing = True
            self.start_norm_pos = self._to_normalized_coords(pos)
            
            # Start a zero-sized rect at start point
            new_rect = QRectF(self.start_norm_pos.x(), self.start_norm_pos.y(), 0.0, 0.0)
            if self.draw_mode == "crop":
                self.crop_rect = new_rect
            else:
                if len(self.ignore_rects) >= 3:
                    # Replace the oldest ignore rect if we exceed 3
                    self.ignore_rects.pop(0)
                self.ignore_rects.append(new_rect)
            self.update()

    def mouseMoveEvent(self, event):
        if not self.is_drawing or not self.start_norm_pos:
            return
        
        pos = event.position()
        curr_norm_pos = self._to_normalized_coords(pos)
        
        # Calculate rect from start and current normalized coords
        x1 = min(self.start_norm_pos.x(), curr_norm_pos.x())
        y1 = min(self.start_norm_pos.y(), curr_norm_pos.y())
        x2 = max(self.start_norm_pos.x(), curr_norm_pos.x())
        y2 = max(self.start_norm_pos.y(), curr_norm_pos.y())
        
        rect = QRectF(x1, y1, x2 - x1, y2 - y1)
        
        if self.draw_mode == "crop":
            self.crop_rect = rect
        else:
            if self.ignore_rects:
                self.ignore_rects[-1] = rect
        self.update()

    def mouseReleaseEvent(self, event):
        self.is_drawing = False
        self.start_norm_pos = None
        
        # Clean up near-zero rects
        if self.draw_mode == "crop":
            if self.crop_rect.width() < 0.01 or self.crop_rect.height() < 0.01:
                self.crop_rect = QRectF(0.0, 0.0, 1.0, 1.0)
        else:
            if self.ignore_rects:
                last_rect = self.ignore_rects[-1]
                if last_rect.width() < 0.01 or last_rect.height() < 0.01:
                    self.ignore_rects.pop()
        self.update()

    def _to_normalized_coords(self, point):
        """Converts widget pixel point to normalized coordinates (0.0 to 1.0) within the image."""
        rx = (point.x() - self.image_rect.x()) / self.image_rect.width()
        ry = (point.y() - self.image_rect.y()) / self.image_rect.height()
        # Bound between 0.0 and 1.0
        rx = max(0.0, min(rx, 1.0))
        ry = max(0.0, min(ry, 1.0))
        return QPointF(rx, ry)

    def _to_widget_coords(self, rect_norm):
        """Converts normalized QRectF to widget pixel QRectF."""
        rx = self.image_rect.x() + rect_norm.x() * self.image_rect.width()
        ry = self.image_rect.y() + rect_norm.y() * self.image_rect.height()
        rw = rect_norm.width() * self.image_rect.width()
        rh = rect_norm.height() * self.image_rect.height()
        return QRectF(rx, ry, rw, rh)
