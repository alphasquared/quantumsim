import numpy as np
import pytools

from . import ptm
import warnings


class DensityNP:

    def __init__(self, dimensions, data=None):

        if len(dimensions) > 15:
            raise ValueError(
                "no_qubits=%d is way too many qubits, are you sure?" %
                no_qubits)

        self.dimensions = dimensions
        self.no_qubits = len(self.dimensions)
        self.size = pytools.product(self.dimensions)
        self.shape = [d**2 for d in dimensions]

        if isinstance(data, np.ndarray):
            single_tensors = [ptm.general_ptm_basis_vector(d)
                    for d in self.dimensions]
            assert data.size == self.size

            data = data.reshape(pytools.flatten(
                [[d,d] for d in self.dimensions))

            in_indices = list(
                reversed(range(self.no_qubits, 3 * self.no_qubits)))
            contraction_indices = [
                (i, i + self.no_qubits, i + 2 * self.no_qubits) for i in range(self.no_qubits)]
            out_indices = list(reversed(range(self.no_qubits)))

            transformation_tensors = list(
                zip(single_tensors, contraction_indices))
            transformation_tensors = pytools.flatten(transformation_tensors)

            self.dm = np.einsum(
                data, in_indices, *transformation_tensors, out_indices, optimize=True).real
        elif data is None:
            self.dm = np.zeros(self.shape)
            self.dm[tuple([0] * self.no_qubits)] = 1
        else:
            raise ValueError("type of data not understood")

    def renormalize(self):
        self.dm = self.dm / self.trace()

    def copy(self):
        cp = DensityNP(self.dimensions)
        cp.dm = self.dm.copy()
        return cp

    def to_array(self):
        single_tensors = [ptm.general_ptm_basis_vector(d)
                for d in self.dimensions]

        in_indices = list(reversed(range(self.no_qubits)))

        idx = [[i, 2 * self.no_qubits - i, 3 * self.no_qubits - i]
               for i in in_indices]

        transformation_tensors = list(single_tensors, idx))
        transformation_tensors = pytools.flatten(transformation_tensors)

        density_matrix = np.einsum(
            self.dm, in_indices, *transformation_tensors, optimize=True)
        density_matrix = density_matrix.reshape(
            (2**self.no_qubits, 2**self.no_qubits))
        return density_matrix

    def get_diag(self):
        no_trace_tensors = []
        for d in self.dimensions:
            ntt = np.zeros(d, d**2)
            ntt[:, :d] = np.eye(d)
            no_trace_tensors.append(ntt)

        trace_argument = []
        for i, ntt in enumerate(no_trace_tensors):
            trace_argument.append(ntt)
            trace_argument.append([i, i + self.no_qubits])

        indices = list(reversed(range(self.no_qubits)))
        out_indices = list(reversed(range(self.no_qubits, 2 * self.no_qubits)))

        return np.einsum(self.dm, indices, *trace_argument, out_indices, optimize=True).reshape(2**self.no_qubits)

    def apply_two_ptm(self, bit0, bit1, two_ptm):

        d0 = self.dimensions[bit0]
        d1 = self.dimensions[bit1]

        two_ptm = two_ptm.reshape((d1, d0, d1, d0))

        dummy_idx0, dummy_idx1 = self.no_qubits, self.no_qubits + 1
        out_indices = list(reversed(range(self.no_qubits)))
        in_indices = list(reversed(range(self.no_qubits)))
        in_indices[self.no_qubits - bit0 - 1] = dummy_idx0
        in_indices[self.no_qubits - bit1 - 1] = dummy_idx1
        two_ptm_indices = [
            bit1, bit0,
            dummy_idx1, dummy_idx0
        ]
        self.dm = np.einsum(
            self.dm, in_indices, two_ptm, two_ptm_indices, out_indices, optimize=True)

    def apply_ptm(self, bit, one_ptm):
        assert bit < self.no_qubits

        dim = self.dimensions[bit]
        assert one_ptm.shape == (dim, dim)

        dummy_idx = self.no_qubits
        out_indices = list(reversed(range(self.no_qubits)))
        in_indices = list(reversed(range(self.no_qubits)))
        in_indices[self.no_qubits - bit - 1] = dummy_idx
        ptm_indices = [bit, dummy_idx]
        self.dm = np.einsum(self.dm, in_indices, one_ptm,
                            ptm_indices, out_indices, optimize=True)

    def add_ancilla(self, anc_st, anc_dim):
        anc_dm = np.zeros(anc_dim**2)
        anc_dm[anc_st] = 1
        self.dm = np.einsum(
            anc_dm, [0], self.dm, list(range(1, self.no_qubits + 1)), optimize=True)
        self.no_qubits = len(self.dm.shape)

    def partial_trace(self, bit):
        if bit >= self.no_qubits:
            raise ValueError("Bit '{}' does not exist".format(bit))

        trace_tensor = np.array([1, 0, 0, 1])
        no_trace_tensor = np.array([[1, 0, 0, 0], [0, 0, 0, 1]])

        trace_argument = []
        for i, d in enumerate(self.dimensions):
            if i == bit:
                ntt = np.zeros(d, d**2)
                ntt[:, :d] = np.eye(d)
                trace_argument.append(ntt)
                trace_argument.append([self.no_qubits + 1, i])
            else:
                tt = np.zeros(d**2)
                tt[:d] = 1
                trace_argument.append(tt)
                trace_argument.append([i])

        indices = list(reversed(range(self.no_qubits)))

        return np.einsum(self.dm, indices, *trace_argument, optimize=True)

    def trace(self):

        trace_argument = []
        for i, d in enumerate(self.dimensions):
            tt = np.zeros(d**2)
            tt[:d] = 1
            trace_argument.append(tt)
            trace_argument.append([i])

        return np.einsum(self.dm, list(range(self.no_qubits)), *trace_argument, optimize=True)

    def project_measurement(self, bit, state):

        assert bit < self.no_qubits

        # the behaviour is a bit weird: swap the MSB to bit and then project
        # out the highest one!
        dim = self.dimensions[bit]
        projector = np.zeros(d**2)
        projector[state] = 1

        in_indices = list(reversed(range(self.no_qubits)))
        projector_indices = [bit]
        out_indices = list(reversed(range(self.no_qubits - 1)))
        if bit != self.no_qubits - 1:
            out_indices[-bit - 1] = self.no_qubits - 1

        self.dm = np.einsum(self.dm, in_indices, projector,
                            projector_indices, out_indices, optimize=True)

        self.no_qubits = len(self.dm.shape)

    def hadamard(self, bit):
        warnings.warn("hadamard deprecated, use apply_ptm", DeprecationWarning)
        self.apply_ptm(bit, ptm.hadamard_ptm())

    def amp_ph_damping(self, bit, gamma, lamda):
        warnings.warn("amp_ph_damping deprecated, use apply_ptm",
                      DeprecationWarning)
        self.apply_ptm(bit, ptm.amp_ph_damping_ptm(gamma, lamda))

    def rotate_y(self, bit, angle):
        warnings.warn("rotate_y deprecated, use apply_ptm", DeprecationWarning)
        self.apply_ptm(bit, ptm.rotate_y_ptm(angle))

    def rotate_x(self, bit, angle):
        warnings.warn("rotate_x deprecated, use apply_ptm", DeprecationWarning)
        self.apply_ptm(bit, ptm.rotate_x_ptm(angle))

    def rotate_z(self, bit, angle):
        warnings.warn("rotate_z deprecated, use apply_ptm", DeprecationWarning)
        self.apply_ptm(bit, ptm.rotate_z_ptm(angle))

    def cphase(self, bit0, bit1):
        assert bit0 < self.no_qubits
        assert bit1 < self.no_qubits

        warnings.warn("cphase deprecated, use apply_ptm", DeprecationWarning)
        two_ptm = ptm.double_kraus_to_ptm(np.diag([1, 1, 1, -1]))
        self.apply_two_ptm(bit0, bit1, two_ptm)