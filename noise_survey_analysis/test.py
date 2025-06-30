import numpy as np

from bokeh.plotting import figure, show
from bokeh.layouts import layout
from bokeh.models import Image, ColumnDataSource, Slider, CustomJS

#dummy data taken from https://docs.bokeh.org/en/2.4.0/docs/gallery/image.html
N = 500
x = np.linspace(0, 10, N)
y = np.linspace(0, 10, N)
xx, yy = np.meshgrid(x, y)
#d1 = first image
d1 = np.sin(xx)*np.cos(yy)
#make a second image
xx, yy = np.meshgrid(x*2, y*2)
d2 = np.sin(xx**2)*np.cos(yy**2)

p = figure(tooltips=[("x", "$x"), ("y", "$y"), ("value", "@im")])
p.x_range.range_padding = p.y_range.range_padding = 0

#initialize a column datasource and assign first image into it
src = ColumnDataSource(data={'x':[0],'y':[0],'dw':[10],'dh':[10],'im':[d1]})
#create the image randerer pointing to the field names in src, and the source itself
im_rend = p.image(image='im', x='x', y='y', dw='dw', dh='dh', palette="Spectral11", level="image",source=src)

p.grid.grid_line_width = 0.5

#a widget to put a callback on
sl = Slider(start=0,end=1,value=0,step=1,width=100)

#the key here is to pass a dictionary to the callback all the information you need to UPDATE the columndatasource that's driving the renderer
# imdict is basically this --> if slider value is 0, i want to get d1, if slider value is 1, i want to get d2
imlist = [{'x':[0],'y':[0],'dw':[10],'dh':[10],'im':[d1]},
          {'x':[3],'y':[2],'dw':[50],'dh':[50],'im':[d2]}
          ]
cb = CustomJS(args=dict(src=src,imlist=imlist,sl=sl),
              code='''
              console.log("[test.py] imlist at sl.value: ", imlist[sl.value]);
              src.data = imlist[sl.value]
              console.log("[test.py] imlist[sl.value]: ", imlist[sl.value]);
              console.log("[test.py] typeof imlist[sl.value].im: ", typeof imlist[sl.value].im);
              src.change.emit()
              ''')
sl.js_on_change('value',cb)
lo = layout([p,sl])
show(lo)