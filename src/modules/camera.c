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

#define CLEAR(x) memset (&(x), 0, sizeof (x))



static int
xioctl (int fd, int request, void * arg)
{
    int r;

    do r = ioctl (fd, request, arg);
    while (-1 == r && EINTR == errno);

    return r;
}

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

struct buffer * buffers       = NULL;
static unsigned int n_buffers = 0;

typedef struct PyDeviceObject {
    PyObject_HEAD
    char* dev_name;                     /* device path */
    int fd;                             /* opened device */
    //struct v4l2_capability cap;
    //struct v4l2_cropcap cropcap;
    //struct buffer* buffers;
    //unsigned int n_buffers;
} PyDeviceObject;

int width = 160;
int height = 120;


/*
 * error related objects
 *
 */

/* standard cameramodule python-error */
static PyObject *CameraError;

/* standard python error object as tuple (err_code, err_msg) */
static PyObject*
format_error (int err_code, char *err_msg)
{
    return Py_BuildValue("(is)", err_code, err_msg);
}

/* common error message builder object */
static char*
errno_msg (const char * s)
{
    char *msg_fmt;
    char *msg_out;

    msg_fmt = "%s error: %s\n";
    msg_out = (char*) malloc((strlen(msg_fmt) + 1 + strlen(strerror(errno))) * sizeof(char));
    sprintf(msg_out, msg_fmt, s, strerror(errno));
    return msg_out;
}


/*
 * retrieve-data functions (python objects)
 *
 */

static PyObject*
device_get_name (PyDeviceObject *self)
{
    return Py_BuildValue("N", PyString_FromString(self->dev_name));
}


/*
 * core functions (non-python objects)
 *
 */

static int process_image(const void* p)
{
    int line, column;
    unsigned char *py, *pu, *pv;
    int r=0, g=0, b=0;
    double area=0;
    int bri=0;

    /* debugging lines (uncomment all debug lines inside the function to
     * proper debug)
     *
     * int cr, cg, cb;
     *
     * FILE *fp;
     * fp = fopen( "/tmp/zacchetepaffete.log", "wb" );
     *
     */

    /* In this format each four bytes is two pixels. Each four bytes is two Y's, a Cb and a Cr.
       Each Y goes to one of* the pixels, and the Cb and Cr belong to both pixels. */
    py = (unsigned char*)p;
    pu = (unsigned char*)p + 1;
    pv = (unsigned char*)p + 3;

    #define CLIP(x) ( (x)>=0xFF ? 0xFF : ( (x) <= 0x00 ? 0x00 : (x) ) )

    for (line = 0; line < height; ++line) {
        for (column = 0; column < width; ++column) {

            r += CLIP((double)*py + 1.402*((double)*pv-128.0));
            g += CLIP((double)*py - 0.344*((double)*pu-128.0) - 0.714*((double)*pv-128.0));
            b += CLIP((double)*py + 1.772*((double)*pu-128.0));

            /* debugging lines
             *
             * cr = CLIP((double)*py + 1.402*((double)*pv-128.0));
             * cg = CLIP((double)*py - 0.344*((double)*pu-128.0) - 0.714*((double)*pv-128.0));
             * cb = CLIP((double)*py + 1.772*((double)*pu-128.0));
             * fprintf(fp, "%d:%d rgb(%d,%d,%d)\n", column + 1, line + 1, cr, cg, cb);
             * r += cr;
             * g += cg;
             * b += cb;
             *
             */

            // increase py every time
            py += 2;

            // increase pu,pv every second time
            if ((column & 1)==1) {
                pu += 4;
                pv += 4;
            }
        }
    }

    area = (width)*(height);
    r = r/area;
    g = g/area;
    b = b/area;
    bri = 0.299 * r + 0.587 * g + 0.114 * b;

    /* debugging lines
     *
     * fprintf(fp, "\n");
     * fprintf(fp, "area: %f\n", area);
     * fprintf(fp, "brightness: %d\n", bri);
     * fclose(fp);
     *
     */

    return bri;
}


static int
init_read (unsigned int buffer_size)
{
    buffers = calloc (1, sizeof (*buffers));

    if (!buffers)
        return 1;

    buffers[0].length = buffer_size;
    buffers[0].start = malloc (buffer_size);

    if (!buffers[0].start)
        return 2;
}


static int
init_mmap (PyDeviceObject *self)
{
    struct v4l2_requestbuffers req;

    CLEAR (req);

    req.count               = 1;
    req.type                = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory              = V4L2_MEMORY_MMAP;

    if (-1 == xioctl (self->fd, VIDIOC_REQBUFS, &req)) {
        if (EINVAL == errno)
            return 1;
        else
            return 2;
    }

    if (req.count < 1)
        return 3;

    buffers = calloc (req.count, sizeof (*buffers));

    if (!buffers)
        return 11;

    for (n_buffers = 0; n_buffers < req.count; ++n_buffers) {
        struct v4l2_buffer buf;

        CLEAR (buf);

        buf.type        = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory      = V4L2_MEMORY_MMAP;
        buf.index       = n_buffers;

        if (-1 == xioctl (self->fd, VIDIOC_QUERYBUF, &buf))
            return 21;

        buffers[n_buffers].length = buf.length;
        buffers[n_buffers].start = mmap (
                NULL /* start anywhere */,
                buf.length,
                PROT_READ | PROT_WRITE /* required */,
                MAP_SHARED /* recommended */,
                self->fd, buf.m.offset);

        if (MAP_FAILED == buffers[n_buffers].start)
            return 31;
    }
}


static int
init_userp (PyDeviceObject *self, unsigned int buffer_size)
{
    struct v4l2_requestbuffers req;
    unsigned int page_size;

    page_size = getpagesize ();
    buffer_size = (buffer_size + page_size - 1) & ~(page_size - 1);

    CLEAR (req);

    req.count               = 1;
    req.type                = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory              = V4L2_MEMORY_USERPTR;

    if (-1 == xioctl (self->fd, VIDIOC_REQBUFS, &req)) {
        if (EINVAL == errno)
            return 1;
        else
            return 2;
    }

    buffers = calloc (1, sizeof (*buffers));

    if (!buffers)
        return 11;

    for (n_buffers = 0; n_buffers < 1; ++n_buffers) {
        buffers[n_buffers].length = buffer_size;
        buffers[n_buffers].start = memalign (/* boundary */ page_size, buffer_size);

        if (!buffers[n_buffers].start)
            return 21;
    }
}




/*
 * core functions (python objects)
 *
 */

static PyObject*
read_frame (PyDeviceObject *self)
{
    struct v4l2_buffer buf;
    unsigned int i;
    int bright=0;

    switch (io) {

        case IO_METHOD_READ:
            if (-1 == read (self->fd, buffers[0].start, buffers[0].length))
                return PyErr_SetFromErrno(CameraError);

            bright = process_image (buffers[0].start);

            break;

        case IO_METHOD_MMAP:
            CLEAR (buf);

            buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
            buf.memory = V4L2_MEMORY_MMAP;

            if (-1 == xioctl (self->fd, VIDIOC_DQBUF, &buf))
                return PyErr_SetFromErrno(CameraError);

            assert (buf.index < n_buffers);

            bright = process_image (buffers[buf.index].start);

            if (-1 == xioctl (self->fd, VIDIOC_QBUF, &buf))
                return PyErr_SetFromErrno(CameraError);

            break;

        case IO_METHOD_USERPTR:
            CLEAR (buf);

            buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
            buf.memory = V4L2_MEMORY_USERPTR;

            if (-1 == xioctl (self->fd, VIDIOC_DQBUF, &buf))
                return PyErr_SetFromErrno(CameraError);

            for (i = 0; i < n_buffers; ++i)
                if (buf.m.userptr == (unsigned long) buffers[i].start
                    && buf.length == buffers[i].length)
                    break;

            assert (i < n_buffers);

            bright = process_image ((void *) buf.m.userptr);

            if (-1 == xioctl (self->fd, VIDIOC_QBUF, &buf))
                return PyErr_SetFromErrno(CameraError);

            break;
    }
    return Py_BuildValue("i", bright);
}



static PyObject*
device_init (PyDeviceObject *self)
{
    struct v4l2_capability cap;
    struct v4l2_cropcap cropcap;
    struct v4l2_crop crop;
    struct v4l2_format fmt;
    unsigned int min;

    char *msg_fmt;
    char *errormessage;

    if (-1 == xioctl (self->fd, VIDIOC_QUERYCAP, &cap)) {
        if (EINVAL == errno) {
            msg_fmt = "'%s' is no V4L2 device\n";
            errormessage = (char*) malloc((strlen(msg_fmt) + 1 + strlen(self->dev_name)) * sizeof(char));
            sprintf(errormessage, msg_fmt, self->dev_name);
            PyErr_SetObject(CameraError, format_error(errno, errormessage));
            return NULL;
        } else {
            PyErr_SetObject(CameraError, format_error(errno, errno_msg("VIDIOC_QUERYCAP")));
            return NULL;
        }
    }

    if (!(cap.capabilities & V4L2_CAP_VIDEO_CAPTURE)) {
        msg_fmt = "'%s' is no video capture device\n";
        errormessage = (char*) malloc((strlen(msg_fmt) + 1 + strlen(self->dev_name)) * sizeof(char));
        sprintf(errormessage, msg_fmt, self->dev_name);
        PyErr_SetObject(CameraError, format_error(0, errormessage));
        return NULL;
    }

    switch (io) {
        case IO_METHOD_READ:
            if (!(cap.capabilities & V4L2_CAP_READWRITE)) {
                msg_fmt = "'%s' does not support read I/O\n";
                errormessage = (char*) malloc((strlen(msg_fmt) + 1 + strlen(self->dev_name)) * sizeof(char));
                sprintf(errormessage, msg_fmt, self->dev_name);
                PyErr_SetObject(CameraError, format_error(0, errormessage));
                return NULL;
            }
            break;

        case IO_METHOD_MMAP:
        case IO_METHOD_USERPTR:
            if (!(cap.capabilities & V4L2_CAP_STREAMING)) {
                msg_fmt = "'%s' does not support streaming I/O\n";
                errormessage = (char*) malloc((strlen(msg_fmt) + 1 + strlen(self->dev_name)) * sizeof(char));
                sprintf(errormessage, msg_fmt, self->dev_name);
                PyErr_SetObject(CameraError, format_error(0, errormessage));
                return NULL;
            }
            break;
    }


    /* Select video input, video standard and tune here. */


    CLEAR (cropcap);

    cropcap.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;

    if (0 == xioctl (self->fd, VIDIOC_CROPCAP, &cropcap)) {
        crop.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        crop.c = cropcap.defrect; /* reset to default */

        if (-1 == xioctl (self->fd, VIDIOC_S_CROP, &crop)) {
            switch (errno) {
                case EINVAL:
                    /* Cropping not supported. */
                    break;
                default:
                    /* Errors ignored. */
                    break;
            }
        }
    } else {
            /* Errors ignored. */
    }


    CLEAR (fmt);

    fmt.type                = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width       = 160;
    fmt.fmt.pix.height      = 120;
    fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_YUYV;
    fmt.fmt.pix.field       = V4L2_FIELD_INTERLACED;

    if (-1 == xioctl (self->fd, VIDIOC_S_FMT, &fmt)) {
        PyErr_SetObject(CameraError, format_error(errno, errno_msg("VIDIOC_S_FMT")));
        return NULL;
    }

    /* Note VIDIOC_S_FMT may change width and height. */

    /* Buggy driver paranoia. */
    min = fmt.fmt.pix.width * 2;
    if (fmt.fmt.pix.bytesperline < min)
        fmt.fmt.pix.bytesperline = min;
    min = fmt.fmt.pix.bytesperline * fmt.fmt.pix.height;
    if (fmt.fmt.pix.sizeimage < min)
        fmt.fmt.pix.sizeimage = min;

    switch (io) {
        case IO_METHOD_READ:
            init_read (fmt.fmt.pix.sizeimage);
            break;

        case IO_METHOD_MMAP:
            init_mmap (self);
            break;

        case IO_METHOD_USERPTR:
            init_userp (self, fmt.fmt.pix.sizeimage);
            break;
    }

    Py_RETURN_NONE;
}



/* Activate a capture session (camera ON) */
static PyObject*
start_capturing (PyDeviceObject *self)
{
    unsigned int i;
    enum v4l2_buf_type type;

    switch (io) {
        case IO_METHOD_READ:
            /* Nothing to do. */
            break;

        case IO_METHOD_MMAP:
            for (i = 0; i < n_buffers; ++i) {
                struct v4l2_buffer buf;

                CLEAR (buf);

                buf.type        = V4L2_BUF_TYPE_VIDEO_CAPTURE;
                buf.memory      = V4L2_MEMORY_MMAP;
                buf.index       = i;

                if (-1 == xioctl (self->fd, VIDIOC_QBUF, &buf)) {
                    PyErr_SetObject(CameraError, format_error(errno, errno_msg("VIDIOC_QBUF")));
                    return NULL;
                }
            }

            type = V4L2_BUF_TYPE_VIDEO_CAPTURE;

            if (-1 == xioctl (self->fd, VIDIOC_STREAMON, &type)) {
                PyErr_SetObject(CameraError, format_error(errno, errno_msg("VIDIOC_STREAMON")));
                return NULL;
            }

            break;

        case IO_METHOD_USERPTR:
            for (i = 0; i < n_buffers; ++i) {
                struct v4l2_buffer buf;

                CLEAR (buf);

                buf.type        = V4L2_BUF_TYPE_VIDEO_CAPTURE;
                buf.memory      = V4L2_MEMORY_USERPTR;
                buf.index       = i;
                buf.m.userptr   = (unsigned long) buffers[i].start;
                buf.length      = buffers[i].length;

                if (-1 == xioctl (self->fd, VIDIOC_QBUF, &buf)) {
                    PyErr_SetObject(CameraError, format_error(errno, errno_msg("VIDIOC_QBUF")));
                    return NULL;
                }
            }

            type = V4L2_BUF_TYPE_VIDEO_CAPTURE;

            if (-1 == xioctl (self->fd, VIDIOC_STREAMON, &type)) {
                PyErr_SetObject(CameraError, format_error(errno, errno_msg("VIDIOC_STREAMON")));
                return NULL;
            }

            break;
    }

    Py_RETURN_NONE;
}



/* Stop a capture session (camera OFF) */
static PyObject*
stop_capturing (PyDeviceObject *self)
{
    enum v4l2_buf_type type;

    switch (io) {
        case IO_METHOD_READ:
            /* Nothing to do. */
            break;

        case IO_METHOD_MMAP:
        case IO_METHOD_USERPTR:
            type = V4L2_BUF_TYPE_VIDEO_CAPTURE;

            if (-1 == xioctl (self->fd, VIDIOC_STREAMOFF, &type)) {
                PyErr_SetObject(CameraError, format_error(errno, errno_msg("VIDIOC_STREAMOFF")));
                return NULL;
            }

            break;
    }

    Py_RETURN_NONE;
}



static PyObject*
device_uninit (PyDeviceObject *self)
{
    unsigned int i;

    switch (io) {
        case IO_METHOD_READ:
            free (buffers[0].start);
            break;

        case IO_METHOD_MMAP:
            for (i = 0; i < n_buffers; ++i)
                if (-1 == munmap (buffers[i].start, buffers[i].length)) {
                    PyErr_SetObject(CameraError, format_error(errno, errno_msg("MUnmap")));
                    return NULL;
                }
            break;

        case IO_METHOD_USERPTR:
            for (i = 0; i < n_buffers; ++i)
                free (buffers[i].start);
            break;
    }

    free (buffers);

    Py_RETURN_NONE;
}



static PyObject*
device_close (PyDeviceObject *self)
{
    if (-1 == close (self->fd)) {
        PyErr_SetObject(CameraError, format_error(errno, errno_msg("Close")));
        return NULL;
    }

    self->fd = -1;

    Py_RETURN_NONE;
}



static PyObject*
device_set (PyDeviceObject *self, PyObject *args)
{
    char* dev_name = NULL;

    if (!PyArg_ParseTuple(args, "s", &dev_name))
        /* raise PyErr (probably TypeError) */
        return NULL;

    if (dev_name == NULL) {
        PyErr_SetObject(CameraError, format_error(0, "Generic memory error: unable to set 'dev_name'\n"));
        return NULL;
    }

    self->dev_name = (char*) malloc((strlen(dev_name) + 1) * sizeof(char));

    if (self->dev_name == NULL) {
        PyErr_SetObject(CameraError, format_error(0, "Generic memory error: unable to set 'self->dev_name'\n"));
        return NULL;
    }

    strcpy(self->dev_name, dev_name);

    Py_RETURN_NONE;
}



static PyObject*
device_open (PyDeviceObject *self)
{
    struct stat st;
    char *msg_fmt;
    char *errormessage;

    if (-1 == stat (self->dev_name, &st)) {
        msg_fmt = "Cannot identify '%s': %s\n";
        errormessage = (char*) malloc((strlen(msg_fmt) + 1 + strlen(self->dev_name) + strlen(strerror(errno))) * sizeof(char));
        sprintf(errormessage, msg_fmt, self->dev_name, strerror(errno));
        PyErr_SetObject(CameraError, format_error(errno, errormessage));
        return NULL;
    }

    if (!S_ISCHR (st.st_mode)) {
        msg_fmt = "'%s' is no device\n";
        errormessage = (char*) malloc((strlen(msg_fmt) + 1 + strlen(self->dev_name)) * sizeof(char));
        sprintf(errormessage, msg_fmt, self->dev_name);
        PyErr_SetObject(CameraError, format_error(0, errormessage));
        return NULL;
    }

    self->fd = open (self->dev_name, O_RDWR /* required */ | O_NONBLOCK, 0);

    if (-1 == self->fd) {
        msg_fmt = "Cannot open '%s': %s\n";
        errormessage = (char*) malloc((strlen(msg_fmt) + 1 + strlen(self->dev_name) + strlen(strerror(errno))) * sizeof(char));
        sprintf(errormessage, msg_fmt, self->dev_name, strerror(errno));
        PyErr_SetObject(CameraError, format_error(errno, errormessage));
        return NULL;
    }

    Py_RETURN_NONE;
}



static PyMethodDef device_methods[] = {
        /* core-global */
        {"setName", (PyCFunction)device_set, METH_VARARGS,
         "Set Device path for camera Device."},
        {"openPath", (PyCFunction)device_open, METH_NOARGS,
         "Open given camera Device."},
        {"initialize", (PyCFunction)device_init, METH_NOARGS,
         "Initialize given camera Device."},
        {"startCapture", (PyCFunction)start_capturing, METH_NOARGS,
         "Start capturing on given camera Device."},
        {"stopCapture", (PyCFunction)stop_capturing, METH_NOARGS,
         "Stop capturing on given camera Device."},
        {"uninitialize", (PyCFunction)device_uninit, METH_NOARGS,
         "Uninitialize given camera Device."},
        {"closePath", (PyCFunction)device_close, METH_NOARGS,
         "Close given camera Device."},
        /* core-actions */
        {"readFrame", (PyCFunction)read_frame, METH_NOARGS,
         "Reads a frame from given camera Device."},
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
    device_methods,                 /* tp_methods        */
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

    CameraError = PyErr_NewException("cameramodule.CameraError", NULL, NULL);
    if (CameraError)
        PyModule_AddObject(m, "Error", CameraError);

    Py_INCREF(&PyDevice_Type);
    PyModule_AddObject(m, "Device", (PyObject *)&PyDevice_Type);
}
