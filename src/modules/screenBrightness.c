#include <Python.h>
#include <stdio.h>
#include <X11/Xlib.h>

/* functions available to module users */
static PyObject* getDisplayBrightness (PyObject* self);

/* functions for internal use */
static int getRootBrightness()
{
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

    display = XOpenDisplay((char *) NULL);

    // window frame size definition
    pct = 0.85;
    w = (int) (pct * XDisplayWidth(display, 0));
    h = (int) (pct * XDisplayHeight(display, 0));
    x = (XDisplayWidth(display, 0) - w) / 2;
    y = (XDisplayHeight(display, 0) - h) / 2;

    root_window=XRootWindow(display, XDefaultScreen(display));
    ximage = XGetImage(display, root_window, x,y, w,h, AllPlanes, ZPixmap);
    if (ximage == (XImage *) NULL)
        return 1;

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

    return (0.299 * r + 0.587 * g + 0.114 * b);
}


static PyObject *
getDisplayBrightness(PyObject *self)
{
    // call brightness function and return int /255 brightness value
    int screenBrightnessValue;
    screenBrightnessValue = getRootBrightness();
    return Py_BuildValue("i", screenBrightnessValue);
}

/* Python related stuff */
static PyMethodDef screenBrightness_funcs[] = {
    {"getDisplayBrightness", (PyCFunction)getDisplayBrightness, METH_NOARGS},
    {NULL}
};

void initscreenBrightness(void)
{
    Py_InitModule3("screenBrightness", screenBrightness_funcs,
                   "Display brightness calculator module");
}
