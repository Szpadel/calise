/*  Copyright (C)   2011-2012   Nicolo' Barbon

    This file is part of Calise.

    Calise is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    any later version.

    Calise is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with Calise.  If not, see <http://www.gnu.org/licenses/>.

*/


#include <Python.h>
#include <stdio.h>
#include <X11/Xlib.h>


/* standard cameramodule python-error */
//static PyObject* ScreenError;


/* functions declaration */
static PyObject* get_brightness (PyObject* self, PyObject *args);
static PyObject* get_size (PyObject* self, PyObject *args);


/* functions */
static PyObject *
get_size(PyObject *self, PyObject *args)
{
    char* screen_name = NULL;

    if (!PyArg_ParseTuple(args, "s", &screen_name))
        return NULL;
    
    Display
        *display;

    int
        xmm, ymm;

    display = XOpenDisplay(screen_name);
    if ( !display )
    {
        return NULL;
    }

    // *real* screen size in mm
    xmm = XDisplayWidthMM(display, 0);
    ymm = XDisplayHeightMM(display, 0);
    
    XCloseDisplay(display);
    
    return Py_BuildValue("ii", xmm, ymm);
}


static PyObject *
get_brightness(PyObject *self, PyObject *args)
{
    char* screen_name = NULL;

    if (!PyArg_ParseTuple(args, "s", &screen_name))
        return NULL;
    
    Display
        *display;

    Window
        root_window;
    XImage
        *ximage;
    int
        x, y,
        w, h;
    int
        p, r=0, g=0, b=0,
        div, area;
    float
        pct;

    display = XOpenDisplay(screen_name);
    if ( !display )
    {
        return NULL;
    }
    
    // window frame size definition
    pct = 0.85;  // arbitrary value for frame crop: only pixels from center to 85% of height/lenght are computed.
    w = (int) (pct * XDisplayWidth(display, 0));
    h = (int) (pct * XDisplayHeight(display, 0));
    x = (XDisplayWidth(display, 0) - w) / 2;
    y = (XDisplayHeight(display, 0) - h) / 2;

    root_window=XRootWindow(display, XDefaultScreen(display));
    ximage = XGetImage(display, root_window, x,y, w,h, AllPlanes, ZPixmap);
    if (ximage == (XImage *) NULL)
        return NULL;

    XCloseDisplay(display);

    // takes 1 pixel every div*div area (div values > 8 will almost not 
    // give performance improvements)
    div = 8;
    int i,k;
    int wmax,hmax;
    wmax = (int) ( (w/div) - 0.49);
    hmax = (int) ( (h/div) - 0.49);
    for (i=0; i<wmax; i++) {
        for (k=0; k<hmax; k++) {

            // obtain r,g,b components from hex(p)
            p = XGetPixel(ximage,div*i,div*k);
            r+=((int) p >> 16) & 0xFF;
            g+=((int) p >> 8) & 0xFF;
            b+=((int) p) & 0xFF;

        }
    }

    XDestroyImage(ximage);

    // average r,g,b components and calculate px brightness on those values
    area = (w/div)*(h/div);
    r = r/area;
    g = g/area;
    b = b/area;

    return Py_BuildValue("f", 0.299 * r + 0.587 * g + 0.114 * b);
}


/* Python related stuff */
static PyMethodDef screen_funcs[] = {
    {"get_brightness", (PyCFunction)getDisplayBrightness, METH_VARARGS},
    {"get_size", (PyCFunction)getDisplaySize, METH_VARARGS},
    {NULL}
};

PyMODINIT_FUNC initscreen(void)
{
    //PyObject* m;

    Py_InitModule3("screen", screen_funcs,
                   "Display brightness calculator module");
    //ScreenError = PyErr_NewException("screenBrightnessmodule.ScreenError", NULL, NULL);
    //if (ScreenError)
    //    PyModule_AddObject(m, "Error", ScreenError);
}
