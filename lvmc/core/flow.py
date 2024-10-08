import torch
from lvmc.core.lattice import Orientation, ParticleLattice


class Flow:
    """Flow class
    a class that handles the flow in the interacting particles system:
    - contains the velocity field of the flow tensor (vx, vy)
    - contains the vorticity field (omega) dx(vy) - dy(vx)
    - computes the migration rate terms due to transport by the flow (using velocity field)
    - computes the reorientation rate terms due to rotation by the flow (using vorticity field)
    """

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.velocity_field = torch.zeros(
            (2, self.height, self.width), dtype=torch.float32
        )
        self.vorticity_field = torch.zeros(
            (self.height, self.width), dtype=torch.float32
        )
        self.obstacles = torch.zeros((self.height, self.width), dtype=torch.bool)

        # add checks later for velocity_field and vorticity_field to be of the right shape

    def compute_tm(self, mask: torch.Tensor):
        """Compute the migration rate terms due to transport by the flow
        :param mask: a tensor of shape (height, width) with 1 for the cells where particles are present and 0 otherwise
        :return: a tensor of shape (height, width, len(Orientation)) with the migration rate terms
        """
        tm = torch.zeros(
            (len(Orientation), self.height, self.width), dtype=torch.float32
        )

        tm[Orientation.RIGHT.value] = (
            self.velocity_field[0, :, :]
            * mask
            * ~mask.roll(shifts=-1, dims=1)
            * (self.velocity_field[0, :, :] > 0)
        )
        tm[Orientation.LEFT.value] = (
            -self.velocity_field[0, :, :]
            * mask
            * ~mask.roll(shifts=1, dims=1)
            * (self.velocity_field[0, :, :] < 0)
        )
        tm[Orientation.UP.value] = (
            self.velocity_field[1, :, :]
            * mask
            * ~mask.roll(shifts=-1, dims=0)
            * (self.velocity_field[1, :, :] > 0)
        )
        tm[Orientation.DOWN.value] = (
            -self.velocity_field[1, :, :]
            * mask
            * ~mask.roll(shifts=1, dims=0)
            * (self.velocity_field[1, :, :] < 0)
        )
        return tm

    def compute_tr(self, lattice: ParticleLattice):
        """Compute the reorientation rate terms due to rotation by the flow
        :param mask: a tensor of shape (height, width) with 1 for the cells where particles are present and 0 otherwise
        :return: a tensor of shape (height, width, len(Orientation)) with the reorientation rate terms
        """
        tr = torch.zeros(
            (len(Orientation), self.height, self.width), dtype=torch.float32
        )

        tr = (
            0.5
            * self.vorticity_field
            * (
                self.positive_vorts * lattice.particles.roll(shifts=1, dims=0)
                ^ (~self.positive_vorts) * lattice.particles.roll(shifts=-1, dims=0)
            )
        )
        return tr

    def set_obstacles(self, obstacles: torch.Tensor):
        """Set the obstacles in the flow
        :param obstacles: a tensor of shape (height, width) with 1 for the cells that are obstacles and 0 otherwise
        """
        self.obstacles = obstacles

    def set_velocity_field(self, velocity_field: torch.Tensor):
        """Set the velocity field
        :param velocity_field: a tensor of shape (height, width, 2) with the velocity field
        """
        self.velocity_field = velocity_field

    def set_vorticity_field(self, vorticity_field: torch.Tensor):
        """Set the vorticity field
        :param vorticity_field: a tensor of shape (height, width) with the vorticity field
        """
        self.vorticity_field = torch.abs(vorticity_field)
        self.positive_vorts = vorticity_field > 0


class PoiseuilleFlow(Flow):
    """PoiseuilleFlow class"""

    def __init__(self, width, height, v1):
        super().__init__(width, height)
        self.v1 = v1
        self.yy = -torch.linspace(
            -1 - 1 / (self.height - 2), 1 + 1 / (self.height - 2), self.height
        )
        self.compute_velocity_field()
        self.compute_vorticity_field()

    def compute_velocity_field(self):
        """Compute the velocity field"""

        self.velocity_field[0, :, :] = (
            (self.v1 * (1 - self.yy**2)).repeat(self.width, 1).T
        )
        self.velocity_field[1, :, :] = 0

    def compute_vorticity_field(self):
        """Compute the vorticity field"""
        self.vorticity_field = (
            2 * self.v1 * self.yy.unsqueeze(1).expand(self.height, self.width)
        )
        self.positive_vorts = self.vorticity_field > 0
        self.vorticity_field = torch.abs(self.vorticity_field)
