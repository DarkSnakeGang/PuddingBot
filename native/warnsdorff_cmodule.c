#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "warnsdorff_dfs_c.h"

static int parse_mask(PyObject *obj, uint64_t *lo, uint64_t *hi) {
    PyObject *idx;
    PyObject *sixtyfour;
    PyObject *shifted;

    idx = PyNumber_Index(obj);
    if (!idx)
        return 0;
    *lo = (uint64_t)PyLong_AsUnsignedLongLongMask(idx);

    sixtyfour = PyLong_FromLong(64);
    if (!sixtyfour) {
        Py_DECREF(idx);
        return 0;
    }
    shifted = PyNumber_Rshift(idx, sixtyfour);
    Py_DECREF(sixtyfour);
    Py_DECREF(idx);
    if (!shifted)
        return 0;
    *hi = (uint64_t)PyLong_AsUnsignedLongLongMask(shifted);
    Py_DECREF(shifted);
    return 1;
}

static PyObject *py_dfs(PyObject *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {
        "head", "rem", "nleft", "black", "required_end",
        "node_limit", "want_path", "use_memo", NULL
    };
    int head, nleft, black;
    PyObject *rem_obj;
    PyObject *required_end_obj = Py_None;
    int node_limit = 0;
    int want_path = 0;
    int use_memo = 0;
    uint64_t rem_lo, rem_hi;
    int required_end = -1;
    int nodes[1] = {0};
    int path[90];
    int path_len = 0;
    int ok;
    PyObject *result;
    int i;

    (void)self;
    if (!PyArg_ParseTupleAndKeywords(
            args, kwargs, "iOii|Oiii", kwlist,
            &head, &rem_obj, &nleft, &black, &required_end_obj,
            &node_limit, &want_path, &use_memo))
        return NULL;

    if (!parse_mask(rem_obj, &rem_lo, &rem_hi))
        return NULL;

    if (required_end_obj != Py_None) {
        required_end = (int)PyLong_AsLong(required_end_obj);
        if (PyErr_Occurred())
            return NULL;
    }

    dfs_init_default_neighbors();
    ok = warnsdorff_dfs_run(
        head, rem_lo, rem_hi, nleft, black, required_end,
        node_limit ? nodes : NULL, node_limit,
        want_path ? path : NULL, want_path ? 90 : 0,
        want_path ? &path_len : NULL,
        use_memo
    );

    if (want_path) {
        if (!ok)
            Py_RETURN_NONE;
        result = PyList_New(path_len);
        if (!result)
            return NULL;
        for (i = 0; i < path_len; i++)
            PyList_SET_ITEM(result, i, PyLong_FromLong(path[i]));
        return result;
    }
    return PyBool_FromLong(ok);
}

static PyMethodDef methods[] = {
    {"dfs", (PyCFunction)py_dfs, METH_VARARGS | METH_KEYWORDS,
     "warnsdorff_dfs_run wrapper"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "warnsdorff_c",
    "Native C Warnsdorff DFS",
    -1,
    methods
};

PyMODINIT_FUNC PyInit_warnsdorff_c(void) {
    dfs_init_default_neighbors();
    return PyModule_Create(&moduledef);
}
