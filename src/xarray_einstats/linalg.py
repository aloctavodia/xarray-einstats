"""Wrappers for :mod:`numpy.linalg`."""
import numpy as np
import xarray as xr

__all__ = ["einsum", "raw_einsum", "einsum_path"]


class MissingMonkeypatchError(Exception):
    """Error specific for the linalg module non-default yet accepted monkeypatch."""


def get_default_dims(da1_dims, d2_dims=None):
    """Get the dimensions corresponding to the matrices.

    Parameters
    ----------
    da1_dims : list of str

    da2_dims : list of str, optional
        Used

    Returns
    -------
    list of str
        The dimensions indicating the matrix dimensions. Must be an iterable
        containing two strings.

    Warnings
    --------
    ``dims`` is required for functions in the linalg module.
    This function acts as a placeholder and only raises an error indicating
    that dims is a required argument unless this function is monkeypatched.
    """
    raise MissingMonkeypatchError()


def _attempt_default_dims(func, da1_dims, da2_dims=None):
    """Raise a more informative warning."""
    try:
        aux = get_default_dims(da1_dims, da2_dims)
    except MissingMonkeypatchError:
        raise TypeError(
            f"{func} missing required argument dims. You must monkeypatch "
            "xarray_einstats.linalg.get_default_dims for dims=None to be supported"
        ) from None
    return aux


class PairHandler:
    def __init__(self, all_dims, keep_dims):
        self.potential_out_dims = keep_dims.union(all_dims)
        self.einsum_axes = list(
            letter
            for letter in "zyxwvutsrqponmlkjihgfedcba"
            if letter not in self.potential_out_dims
        )
        self.dim_map = {d: self.einsum_axes.pop() for d in all_dims}
        self.out_dims = []
        self.out_subscript = ""
        self.ellipsis = False

    def process_dim_da_pair(self, da, dim_sublist):
        da_dims = da.dims
        out_dims = [
            dim for dim in da_dims if dim in self.potential_out_dims and dim not in dim_sublist
        ]
        subscripts = ""
        updated_in_dims = dim_sublist.copy()
        for dim in out_dims:
            self.out_dims.append(dim)
            sub = self.einsum_axes.pop()
            self.out_subscript += sub
            subscripts += sub
            updated_in_dims.insert(0, dim)
        for dim in dim_sublist:
            subscripts += self.dim_map[dim]
        if len(da_dims) > len(out_dims) + len(dim_sublist):
            self.ellipsis = True
            return f"...{subscripts}", updated_in_dims
        return subscripts, updated_in_dims

    def get_out_subscript(self):
        if not self.out_subscript:
            return ""
        if self.ellipsis:
            return f"->...{self.out_subscript}"
        return f"->{self.out_subscript}"


def _einsum_parent(dims, *operands, keep_dims=frozenset()):
    """Preprocess inputs to call :func:`numpy.einsum` or :func:`numpy.einsum_path`.

    Parameters
    ----------
    dims : list of list of str
        List of lists of dimension names. It must have the same length or be
        only one item longer than ``operands``. If both have the same
        length, the generated pattern passed to {func}`numpy.einsum`
        won't have ``->`` nor right hand side. Otherwise, the last
        item is assumed to be the dimension specification of the output
        DataArray, and it can be an empty list to add ``->`` but no
        subscripts.
    operands : DataArray
        DataArrays for the operation. Multiple DataArrays are accepted.
    keep_dims : set, optional
        Dimensions to exclude from summation unless specifically specified in ``dims``

    See Also
    --------
    xarray_einstats.einsum, xarray_einstats.einsum_path
    numpy.einsum, numpy.einsum_path
    xarray_einstats.einops.reduce
    """
    if len(dims) == len(operands):
        in_dims = dims
        out_dims = None
    elif len(dims) == len(operands) + 1:
        in_dims = dims[:-1]
        out_dims = dims[-1]
    else:
        raise ValueError("length of dims and operands not compatible")

    all_dims = set(dim for sublist in dims for dim in sublist)
    handler = PairHandler(all_dims, keep_dims)
    in_subscripts = []
    updated_in_dims = []
    for da, sublist in zip(operands, in_dims):
        in_subs, up_dims = handler.process_dim_da_pair(da, sublist)
        in_subscripts.append(in_subs)
        updated_in_dims.append(up_dims)

    if out_dims is None:
        out_subscript = handler.get_out_subscript()
        out_dims = handler.out_dims
    elif not out_dims:
        out_subscript = "->"
    else:
        out_subscript = "->" + "".join(handler.dim_map[dim] for dim in out_dims)
    subscripts = ",".join(in_subscripts) + out_subscript
    return subscripts, updated_in_dims, out_dims


def einsum_path(dims, *operands, keep_dims=frozenset(), optimize=None, **kwargs):
    """Wrap :func:`numpy.einsum_path`.

    See :func:`xarray_einstats.einsum` for a detailed description of ``dims``
    and ``operands``.

    Parameters
    ----------
    dims : list of list of str
    operands : DataArray
    optimize : str, optional
        ``optimize`` argument for :func:`numpy.einsum_path`. It defaults to None so that
        we always default to numpy's default, without needing to keep the call signature
        here up to date.
    kwargs : dict, optional
        Passed to :func:`xarray.apply_ufunc`
    """
    op_kwargs = {} if optimize is None else dict(optimize=optimize)

    subscripts, in_dims, _ = _einsum_parent(dims, *operands, keep_dims=keep_dims)
    updated_in_dims = []
    for sublist, da in zip(in_dims, operands):
        updated_in_dims.append([dim for dim in da.dims if dim not in sublist] + sublist)

    return xr.apply_ufunc(
        np.einsum_path,
        subscripts,
        *operands,
        input_core_dims=[[], *updated_in_dims],
        output_core_dims=[[]],
        kwargs=op_kwargs,
        **kwargs,
    ).values.item()


def einsum(dims, *operands, keep_dims=frozenset(), out_append="{i}", einsum_kwargs=None, **kwargs):
    """Preprocess inputs to call :func:`numpy.einsum` or :func:`numpy.einsum_path`.

    Parameters
    ----------
    dims : list of list of str
        List of lists of dimension names. It must have the same length or be
        only one item longer than ``operands``. If both have the same
        length, the generated pattern passed to {func}`numpy.einsum`
        won't have ``->`` nor right hand side. Otherwise, the last
        item is assumed to be the dimension specification of the output
        DataArray, and it can be an empty list to add ``->`` but no
        subscripts.
    operands : DataArray
        DataArrays for the operation. Multiple DataArrays are accepted.
    keep_dims : set, optional
        Dimensions to exclude from summation unless specifically specified in ``dims``
    out_append : str, default "{i}"
        Pattern to append to repeated dimension names in the output (if any). The pattern should
        contain a substitution for variable ``i``, which indicates the number of the current
        dimension among the repeated ones. To keep repeated dimension names use ``""``.

        The first occurrence will keep the original name and will therefore inherit the
        coordinate values in case there are any.
    einsum_kwargs : dict, optional
        Passed to :func:`numpy.einsum`
    kwargs : dict, optional
        Passed to :func:`xarray.apply_ufunc`

    Notes
    -----
    Dimensions present in ``dims`` will be reduced, but unlike {func}`xarray.dot` it does so only
    for that variable.
    """
    if einsum_kwargs is None:
        einsum_kwargs = {}

    subscripts, updated_in_dims, out_dims = _einsum_parent(dims, *operands, keep_dims=keep_dims)

    updated_out_dims = []
    for i, dim in enumerate(out_dims):
        totalcount = out_dims.count(dim)
        count = out_dims[:i].count(dim) + 1
        updated_out_dims.append(
            dim + out_append.format(i=count) if (totalcount > 1) and (count > 1) else dim
        )
    return xr.apply_ufunc(
        np.einsum,
        subscripts,
        *operands,
        input_core_dims=[[], *updated_in_dims],
        output_core_dims=[updated_out_dims],
        kwargs=einsum_kwargs,
        **kwargs,
    )


def raw_einsum(
    subscripts, *operands, keep_dims=frozenset(), out_append="{i}", einsum_kwargs=None, **kwargs
):
    """Wrap :func:`numpy.einsum` crudely.

    Parameters
    ----------
    subscripts : str
        Specify the subscripts for the summation as dimension names. Spaces indicate
        multiple dimensions in a DataArray and commas indicate multiple DataArray
        operands. Only dimensions with no spaces, nor commas nor ``->`` characters
        are valid.
    operands : DataArray
    ...
    """
    if "->" in subscripts:
        in_subscripts, out_subscript = subscripts.split("->")
    else:
        in_subscripts = subscripts
        out_subscript = None
    in_dims = [
        [dim.strip(", ") for dim in in_subscript.split(" ")]
        for in_subscript in in_subscripts.split(",")
    ]
    if out_subscript is None:
        dims = in_dims
    elif not out_subscript:
        dims = [*in_dims, []]
    else:
        out_dims = [dim.strip(", ") for dim in out_subscript.split(" ")]
        dims = in_dims + out_dims
    return einsum(
        dims,
        *operands,
        keep_dims=keep_dims,
        out_append=out_append,
        einsum_kwargs=einsum_kwargs,
        **kwargs,
    )


def matrix_power(da, n, dims=None, **kwargs):
    """Wrap :func:`numpy.linalg.matrix_power`.

    Description of arguments at :ref:`linalg_reference`
    """
    if dims is None:
        dims = _attempt_default_dims("matrix_power", da.dims)
    return xr.apply_ufunc(
        np.linalg.matrix_power, da, n, input_core_dims=[dims, []], output_core_dims=[dims], **kwargs
    )


def cholesky(da, dims=None, **kwargs):
    """Wrap :func:`numpy.linalg.cholesky`.

    Description of arguments at :ref:`linalg_reference`
    """
    if dims is None:
        dims = _attempt_default_dims("cholesky", da.dims)
    return xr.apply_ufunc(
        np.linalg.cholesky, da, input_core_dims=[dims], output_core_dims=[dims], **kwargs
    )


def qr(da, dims=None, mode="reduced", out_append="2", **kwargs):  # pylint: disable=invalid-name
    """Wrap :func:`numpy.linalg.qr`.

    Description of arguments at :ref:`linalg_reference`
    """
    if dims is None:
        dims = _attempt_default_dims("qr", da.dims)
    m_dim, n_dim = dims
    m, n = len(da[m_dim]), len(da[n_dim])
    k = min(m, n)
    mode = mode.lower()
    if mode == "reduced":
        if m == k:
            out_dims = [[m_dim, m_dim + out_append], [m_dim, n_dim]]
        else:
            out_dims = [[m_dim, n_dim], [n_dim, n_dim + out_append]]
    elif mode == "complete":
        out_dims = [[m_dim, m_dim + out_append], [m_dim, n_dim]]
    elif mode == "r":
        out_dims = [[m_dim if k == m else n_dim + out_append, n_dim]]
    elif mode == "raw":
        out_dims = [[n_dim, m_dim], [m_dim if k == m else n_dim]]
    else:
        raise ValueError("mode not recognized")

    return xr.apply_ufunc(
        np.linalg.qr,
        da,
        input_core_dims=[dims],
        output_core_dims=out_dims,
        kwargs=dict(mode=mode),
        **kwargs,
    )


def svd(
    da, dims=None, full_matrices=True, compute_uv=True, hermitian=False, out_append="2", **kwargs
):
    """Wrap :func:`numpy.linalg.svd`."""
    if dims is None:
        dims = _attempt_default_dims("svd", da.dims)
    m_dim, n_dim = dims
    m, n = len(da[m_dim]), len(da[n_dim])
    k = min(m, n)
    k_dim = m_dim if k == m else n_dim
    s_dims = [k_dim]
    if full_matrices:
        u_dims = [m_dim, m_dim + out_append]
        vh_dims = [n_dim, n_dim + out_append]
    else:
        if m == k:
            u_dims = [m_dim, k_dim + out_append]
            vh_dims = [k_dim, n_dim]
        else:
            u_dims = [m_dim, k_dim]
            vh_dims = [k_dim, n_dim + out_append]
    if compute_uv:
        out_dims = [u_dims, s_dims, vh_dims]
    else:
        out_dims = [s_dims]
    return xr.apply_ufunc(
        np.linalg.svd,
        da,
        input_core_dims=[dims],
        output_core_dims=out_dims,
        kwargs=dict(full_matrices=full_matrices, compute_uv=compute_uv, hermitian=hermitian),
        **kwargs,
    )


def eig(da, dims=None, **kwargs):
    """Wrap :func:`numpy.linalg.eig`."""
    if dims is None:
        dims = _attempt_default_dims("eig", da.dims)
    return xr.apply_ufunc(
        np.linalg.eig, da, input_core_dims=[dims], output_core_dims=[dims[:1], dims], **kwargs
    )


def eigh(da, dims=None, UPLO="L", **kwargs):  # pylint: disable=invalid-name
    """Wrap :func:`numpy.linalg.eigh`."""
    if dims is None:
        dims = _attempt_default_dims("eigh", da.dims)
    return xr.apply_ufunc(
        np.linalg.eigh,
        da,
        input_core_dims=[dims],
        output_core_dims=[dims[:1], dims],
        kwargs=dict(UPLO=UPLO),
        **kwargs,
    )


def eigvals(da, dims=None, **kwargs):
    """Wrap :func:`numpy.linalg.eigvals`."""
    if dims is None:
        dims = _attempt_default_dims("eigvals", da.dims)
    return xr.apply_ufunc(
        np.linalg.eigvals, da, input_core_dims=[dims], output_core_dims=[dims[:1]], **kwargs
    )


def eigvalsh(da, dims=None, UPLO="L", **kwargs):  # pylint: disable=invalid-name
    """Wrap :func:`numpy.linalg.eigvalsh`."""
    if dims is None:
        dims = _attempt_default_dims("eigvalsh", da.dims)
    return xr.apply_ufunc(
        np.linalg.eigvalsh,
        da,
        input_core_dims=[dims],
        output_core_dims=[dims[:1]],
        kwargs=dict(UPLO=UPLO),
        **kwargs,
    )


def norm(da, dims=None, ord=None, **kwargs):  # pylint: disable=redefined-builtin
    """Wrap :func:`numpy.linalg.norm`."""
    if dims is None:
        dims = _attempt_default_dims("norm", da.dims)
    norm_kwargs = {"ord": ord}
    if isinstance(dims, str):
        in_dims = [dims]
        norm_kwargs["axis"] = -1
    else:
        in_dims = dims
        norm_kwargs["axis"] = (-2, -1)
    return xr.apply_ufunc(
        np.linalg.norm, da, input_core_dims=[in_dims], kwargs=norm_kwargs, **kwargs
    )


def cond(da, dims=None, p=None, **kwargs):  # pylint: disable=invalid-name
    """Wrap :func:`numpy.linalg.cond`."""
    if dims is None:
        dims = _attempt_default_dims("cond", da.dims)
    return xr.apply_ufunc(np.linalg.cond, da, input_core_dims=[dims], kwargs=dict(p=p), **kwargs)


def det(da, dims=None, **kwargs):
    """Wrap :func:`numpy.linalg.det`."""
    if dims is None:
        dims = _attempt_default_dims("det", da.dims)
    return xr.apply_ufunc(np.linalg.det, da, input_core_dims=[dims], **kwargs)


def matrix_rank(da, dims=None, tol=None, hermitian=False, **kwargs):
    """Wrap :func:`numpy.linalg.matrix_rank`."""
    if dims is None:
        dims = _attempt_default_dims("matrix_rank", da.dims)
    return xr.apply_ufunc(
        np.linalg.matrix_rank,
        da,
        input_core_dims=[dims],
        kwargs=dict(tol=tol, hermitian=hermitian),
        **kwargs,
    )


def slogdet(da, dims=None, **kwargs):
    """Wrap :func:`numpy.linalg.slogdet`."""
    if dims is None:
        dims = _attempt_default_dims("slogdet", da.dims)
    return xr.apply_ufunc(
        np.linalg.slogdet, da, input_core_dims=[dims], output_core_dims=[[], []], **kwargs
    )


def trace(da, dims=None, offset=None, dtype=None, out=None, **kwargs):
    """Wrap :func:`numpy.trace`."""
    if dims is None:
        dims = _attempt_default_dims("trace", da.dims)
    trace_kwargs = dict(offset=offset, dtype=dtype, out=out, axis1=-2, axis2=-1)
    return xr.apply_ufunc(np.trace, da, input_core_dims=[dims], kwargs=trace_kwargs, **kwargs)


def solve(da, db, dims=None, **kwargs):
    """Wrap :func:`numpy.linalg.solve`.

    Here dims can be of length 3 to indicate
    """
    if dims is None:
        dims = _attempt_default_dims("solve", da.dims, db.dims)
    if len(dims) == 3:
        b_dim = dims[0] if dims[0] in db.dims else dims[1]
        in_dims = [dims[:2], [b_dim, dims[-1]]]
        out_dims = [[b_dim, dims[-1]]]
    else:
        in_dims = [dims, dims[:1]]
        out_dims = [dims[:1]]
    return xr.apply_ufunc(
        np.linalg.solve, da, db, input_core_dims=in_dims, output_core_dims=out_dims, **kwargs
    )


def inv(da, dims=None, **kwargs):
    """Wrap :func:`numpy.linalg.inv`."""
    if dims is None:
        dims = _attempt_default_dims("inv", da.dims)
    return xr.apply_ufunc(
        np.linalg.inv, da, input_core_dims=[dims], output_core_dims=[dims], **kwargs
    )
