#include <Python.h>
/* #include <structmember.h> */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>

#include <fcntl.h>              /* low-level i/o */
#include <unistd.h>
#include <errno.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/time.h>
#include <sys/mman.h>
#include <sys/ioctl.h>

#include <asm/types.h>          /* for videodev2.h */

#include <linux/videodev2.h>



typedef enum {
    IO_METHOD_READ,
    IO_METHOD_MMAP,
    IO_METHOD_USERPTR,
} io_method;

static io_method io = IO_METHOD_MMAP;










struct buffer {
    void * start;
    size_t length;
};


typedef struct PyDeviceObject {
    PyObject_HEAD
    char* dev_name;                     /* device path */
    int fd;                             /* opened device */
    struct v4l2_capability cap;
    struct v4l2_cropcap cropcap;
    struct buffer* buffers;
    unsigned int n_buffers;
} PyDeviceObject;


/*
 * retrieve-data functions
 *
 */

static PyObject*
device_get_name (PyDeviceObject *self)
{
    return Py_BuildValue("N", PyString_FromString(self->dev_name));
}


/*
 * core functions
 *
 */

static PyObject*
device_init (PyDeviceObject *self, PyObject *args)
{
    char* dev_name = NULL;

    if (!PyArg_ParseTuple(args, "s", &dev_name))
        return Py_BuildValue("i", 1);

    if (dev_name == NULL)
        return Py_BuildValue("i", 2);

    self->dev_name = (char*) malloc((strlen(dev_name) + 1) * sizeof(char));

    if (self->dev_name == NULL)
        return Py_BuildValue("i", 3);

    strcpy(self->dev_name, dev_name);

    return Py_BuildValue("i", 0);
}


static PyObject*
device_open (PyDeviceObject *self)
{
    struct stat st;

    if (-1 == stat (self->dev_name, &st)) {
        return Py_BuildValue("i", 1);
    }

    if (!S_ISCHR (st.st_mode)) {
        return Py_BuildValue("i", 2);
    }

    self->fd = open (self->dev_name, O_RDWR /* required */ | O_NONBLOCK, 0);

    if (-1 == self->fd) {
        return Py_BuildValue("i", 3);
    }

    return Py_BuildValue("i", 0);
}


static PyMethodDef device_methods[] = {
        /* core */
        {"initialize", (PyCFunction)device_init, METH_VARARGS,
         "Initialize given camera Device."},
         {"openPath", (PyCFunction)device_open, METH_VARARGS,
         "Open given camera Device."},
         /* other */
        {"getName", (PyCFunction)device_get_name, METH_NOARGS,
         "Grab dev_name from camera Device."},
        {NULL}
};

static PyTypeObject PyDevice_Type = {
    PyObject_HEAD_INIT(NULL)
    0,                              /* ob_size           */
    "camera.Device",                /* tp_name           */
    sizeof(PyDeviceObject),         /* tp_basicsize      */
    0,                              /* tp_itemsize       */
    0,                              /* tp_dealloc        */
    0,                              /* tp_print          */
    0,                              /* tp_getattr        */
    0,                              /* tp_setattr        */
    0,                              /* tp_compare        */
    0,                              /* tp_repr           */
    0,                              /* tp_as_number      */
    0,                              /* tp_as_sequence    */
    0,                              /* tp_as_mapping     */
    0,                              /* tp_hash           */
    0,                              /* tp_call           */
    0,                              /* tp_str            */
    0,                              /* tp_getattro       */
    0,                              /* tp_setattro       */
    0,                              /* tp_as_buffer      */
    Py_TPFLAGS_DEFAULT,             /* tp_flags          */
    0, //Name_doc,                       /* tp_doc            */
    0,                              /* tp_traverse       */
    0,                              /* tp_clear          */
    0,                              /* tp_richcompare    */
    0,                              /* tp_weaklistoffset */
    0,                              /* tp_iter           */
    0,                              /* tp_iternext       */
    device_methods,                   /* tp_methods        */
    0, //Name_members,                   /* tp_members        */
    0,                              /* tp_getset         */
    0,                              /* tp_base           */
    0,                              /* tp_dict           */
    0,                              /* tp_descr_get      */
    0,                              /* tp_descr_set      */
    0,                              /* tp_dictoffset     */
    0, //(initproc)device_init,          /* tp_init           */
};





PyMODINIT_FUNC initcamera (void)
{
    PyObject* m;
    char* dev_name = NULL;

    //PyArg_ParseTuple(arg, "s", &dev_name);

    PyDevice_Type.tp_new = PyType_GenericNew;
    if (PyType_Ready(&PyDevice_Type) < 0)
        return;

    m = Py_InitModule3("camera", NULL,
                       "Example module that creates an extension type.");
    if (m == NULL)
        return;

    Py_INCREF(&PyDevice_Type);
    PyModule_AddObject(m, "device", (PyObject *)&PyDevice_Type);
}
