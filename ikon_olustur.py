import sys, struct
from PyQt5.QtGui import QGuiApplication, QImage, QPainter, QColor, QPen, QFont, QLinearGradient
from PyQt5.QtCore import Qt, QBuffer, QIODevice

app = QGuiApplication(sys.argv)

boyut = 256
img = QImage(boyut, boyut, QImage.Format_ARGB32)
img.fill(Qt.transparent)

p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)

grad = QLinearGradient(0, 0, boyut, boyut)
grad.setColorAt(0, QColor("#0d1520"))
grad.setColorAt(1, QColor("#05070a"))
p.setBrush(grad)
p.setPen(QPen(QColor("#00d2ff"), 10))
p.drawRoundedRect(12, 12, boyut - 24, boyut - 24, 44, 44)

p.setPen(QPen(QColor("#ffaa00"), 4))
p.drawRoundedRect(26, 26, boyut - 52, boyut - 52, 32, 32)

p.setPen(QColor("#00d2ff"))
p.setFont(QFont("Bahnschrift", 135, QFont.Bold))
p.drawText(img.rect(), Qt.AlignCenter, "D")
p.end()

buf = QBuffer()
buf.open(QIODevice.WriteOnly)
img.save(buf, "PNG")
png_veri = bytes(buf.data())

baslik = struct.pack("<HHH", 0, 1, 1)
giris = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png_veri), 22)

with open("dodni.ico", "wb") as f:
    f.write(baslik + giris + png_veri)

print("dodni.ico basariyla olusturuldu.")