import torch
import torch.nn.functional as F
import numpy as np
from enum import Enum
from typing import List, Tuple, Optional, Union
import copy

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")


class Orientation(Enum):
    EMPTY = -1
    UP = 0
    LEFT = 1
    DOWN = 2
    RIGHT = 3


class ParticleLattice:
    """
    Class for the particle lattice.
    """

    ############################################
    ## Initialization and Basic Configuration ##
    ############################################

    def __init__(
        self, width: int, height: int, generator: torch.Generator = None, dim=2
    ):
        """
        Initialize the particle lattice.
        :param width: Width of the lattice.
        :param height: Height of the lattice.
        :param density: Density of particles in the lattice
        """
        self.width = width
        self.height = height
        self.generator = generator

        # Initialize the paricles lattice as a 3D tensor with dimensions corresponding to
        # orientations, width, and height.
        self.particles = torch.zeros(
            (height, width, dim), dtype=torch.int8, device=device
        )
        self.obstacles = torch.zeros((height, width), dtype=torch.bool, device=device)
        self.sinks = torch.zeros((height, width), dtype=torch.bool, device=device)

        # Particle tracking
        self.id_to_position = {}  # Dictionary to track particles
        self.position_to_particle_id = {}  # Dictionary to map positions to particle IDs
        self.next_particle_id = 0  # Counter to assign unique IDs to particles

        # Precompute deltas for each spin value
        self.orientation_deltas = {
            Orientation.UP: (0, -1),
            Orientation.DOWN: (0, 1),
            Orientation.LEFT: (-1, 0),
            Orientation.RIGHT: (1, 0),
            Orientation.EMPTY: (0, 0),
        }

        # Initialize the orientation map
        self.orientation_map = np.empty((height, width), dtype=Orientation)
        # Initialize the occupancy map
        self.occupancy_map = torch.zeros(
            (height, width), dtype=torch.bool, device=device
        )
    
    def add_particles(self, **kwargs) -> None:
        """
        Add particles to the lattice. The particles can be added using the following methods:
        - density: Add particles at a given density.
        - spins: Add particles with specific spins.
        - region: Add particles in a specific region. The region is specified as a tuple of (x1, y1, x2, y2).
        :param density: Density of particles to be initialized.
        :param spins: A tensor of spins to initialize the lattice.
        :param region: A tuple of (x1, y1, x2, y2) representing the region where particles will be added.
        :param orientation: The orientation of the particles.
        """
        if "density" in kwargs:
            self.populate(kwargs["density"])
        
        if "spins" in kwargs:
            spins = kwargs["spins"]
            # Validate the shape of the spins tensor
            if spins.shape[:-1] != (self.height, self.width):
                raise ValueError(
                    f"Spins tensor must match the lattice dimensions. \n >>> {spins.shape=}, {(self.height, self.width)=}"
                )
            self.particles = spins
        
        if "region" in kwargs:
            region = kwargs["region"]
            orientation = kwargs.get("orientation", None)
            n_particles = kwargs.get("n_particles", 1)
            self.add_particle_flux(region, orientation, n_particles)
        return self

    def get_params(self) -> dict:
        """
        Get the parameters of the lattice.
        :return: A dictionary of the lattice parameters.
        """
        return {
            "width": self.width,
            "height": self.height,
        }

    ###################################
    ## Lattice Configuration Methods ##
    ###################################
    def populate(self, density: float, verbose: bool = False) -> None:
        """
        Populate the lattice with particles at a given density.

        :param density: Density of particles to be initialized.
        """
        n_added = self._populate(density)
        if verbose:
            print(f"Added {n_added} particles to the lattice.")
        return self
            

    ####################################
    ## Validation and utility methods ##
    ####################################

    def _validate_coordinates(self, x: int, y: int):
        """
        Validate the coordinates to ensure they are within the lattice bounds.

        Parameters:
        x (int): x-coordinate to validate.
        y (int): y-coordinate to validate.

        Raises:
        ValueError: If the coordinates are outside the lattice bounds, specifying the invalid coordinates.
        """

        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            raise IndexError(f"Coordinates ({x}, {y}) are out of lattice bounds.")

    def _create_index_to_symbol_mapping(self) -> dict:
        """
        Create a mapping between orientation indices and symbols for visualization.
        :return: A dictionary mapping orientation indices to symbols.
        """
        # Map each Orientation enum value to its corresponding symbol
        return {
            Orientation.UP.value: "↑",
            Orientation.DOWN.value: "↓",
            Orientation.LEFT.value: "←",
            Orientation.RIGHT.value: "→",
            Orientation.EMPTY.value: "·",
        }

    def _is_empty(self, x: int, y: int) -> bool:
        """
        Check if a cell is empty.

        :param x: x-coordinate of the lattice.
        :param y: y-coordinate of the lattice.
        :return: True if the no particle is present at the cell, False otherwise.
        """
        return not self.particles[y, x].any()


    def _get_target_position(
        self, x: int, y: int, orientation: Optional[Orientation]
    ) -> tuple:
        """
        Get the expected position of a particle at (x, y) with a given orientation.

        :param orientation: The orientation of the particle.
        :param x: Current x-coordinate of the particle.
        :param y: Current y-coordinate of the particle.
        :param orientation: The direction in which the particle is moving.
        :return: The expected position of the particle.
        """

        # Validate coordinates
        self._validate_coordinates(x, y)

        # Validate occupancy
        self._validate_occupancy(x, y)

        # Calculate new position based on orientation
        delta_x, delta_y = self.orientation_deltas[orientation]
        new_x, new_y = (x + delta_x) % self.width, (y + delta_y) % self.height
        return new_x, new_y

    def _is_obstacle(self, x: int, y: int) -> bool:
        """
        Check if the specified cell is an obstacle.

        Parameters:
        x (int): x-coordinate of the cell in the lattice.
        y (int): y-coordinate of the cell in the lattice.

        Returns:
        bool: True if the cell is an obstacle, False otherwise.

        Raises:
        ValueError: If the coordinates are out of the lattice bounds.
        """
        self._validate_coordinates(x, y)
        return self.obstacles[y, x] == 1

    def _is_sink(self, x: int, y: int) -> bool:
        """
        Check if the specified cell is a sink.

        Parameters:
        x (int): x-coordinate of the cell in the lattice.
        y (int): y-coordinate of the cell in the lattice.

        Returns:
        bool: True if the cell is a sink, False otherwise.

        Raises:
        IndexError: If the coordinates are out of the lattice bounds.
        """
        self._validate_coordinates(x, y)
        return self.sinks[y, x] == 1

    def _validate_availability(self, x: int, y: int) -> None:
        """
        Validate that the specified cell is available for particle movement.

        Parameters:
        x (int): x-coordinate of the cell in the lattice.
        y (int): y-coordinate of the cell in the lattice.

        Raises:
        IndexError: If the coordinates are out of the lattice bounds.
        ValueError: If the specified cell is an obstacle.
        ValueError: If the specified cell is a non-empty.
        """

        self._validate_coordinates(x, y)
        if self._is_obstacle(x, y):
            raise ValueError(f"Site ({x}, {y}) is an obstacle.")
        if not self._is_empty(x, y):
            raise ValueError(f"Site ({x}, {y}) is not empty.")

    def _validate_occupancy(self, x: int, y: int) -> None:
        """
        Validate that the specified cell is occupied by a particle.

        Parameters:
        x (int): x-coordinate of the cell in the lattice.
        y (int): y-coordinate of the cell in the lattice.

        Raises:
        IndexError: If the coordinates are out of the lattice bounds.
        ValueError: If the specified cell is empty.
        """

        self._validate_coordinates(x, y)
        if self._is_empty(x, y):
            raise ValueError(f"Site ({x}, {y}) is empty.")

    def _update_tracking(self, id: int, x: int, y: int) -> None:
        """
        Update the particle tracking dictionaries.
        :param id: The id of the particle.
        :param x: The x-coordinate of the particle.
        """
        self.id_to_position[id] = (x, y)
        self.position_to_particle_id[(x, y)] = id

    @property
    def shape(self):
        """
        Returns the shape (height, width) of the lattice.
        """
        return (self.height, self.width)

    @property
    def density(self):
        """
        Returns the density of the lattice, calculated as the ratio of occupied cells to total cells.
        """
        num_occupied_cells = (
            self.particles.any(dim=0).sum().item()
        )  # Count occupied cells
        total_cells = self.width * self.height - self.obstacles.sum().item()
        return num_occupied_cells / total_cells if total_cells > 0 else 0

    @property
    def n_particles(self):
        return self.particles.abs().sum().item()

    @property
    def is_empty(self):
        return torch.all(~self.occupancy_map)

    ###################################
    ## Particle Manipulation Methods ##
    ###################################

    def add_particle(self, x: int, y: int, orientation: Orientation = None) -> None:
        """
        Add a particle with a specific orientation at (x, y).

        :param x: x-coordinate of the lattice.
        :param y: y-coordinate of the lattice.
        :param orientation: Orientation of the particle, as an instance of the Orientation enum.
        """
        # Validate that orientation is an instance of Orientation
        if orientation is None:
            ori_ind = torch.randint(
                0, 4, (1,), device=device, generator=self.generator
            ).item()
            orientation = Orientation(ori_ind)

        if not isinstance(orientation, Orientation):
            if not isinstance(orientation, int):
                raise ValueError(
                    "orientation must be an instance of Orientation enum or an integer."
                )
            else:
                orientation = Orientation(orientation)

        # Validate that the specified cell is available for particle movement
        self._validate_availability(x, y)

        self.particles[y, x] = torch.tensor(
            self.orientation_deltas[orientation]
        )  # Add particle to the lattice
        self.orientation_map[y, x] = orientation
        self.occupancy_map[y, x] = True

        self._update_tracking(
            self.next_particle_id, x, y
        )  # update the particle tracking dictionaries

        self.next_particle_id += 1  # increment the next particle id

    def remove_particle(self, x: int, y: int) -> None:
        """
        Remove a particle from a specific node in the lattice.

        :param x: x-coordinate of the node.
        :param y: y-coordinate of the node.
        """
        # Validate coordinates
        self._validate_coordinates(x, y)
        self.particles[y, x] = 0  # Remove particle from the lattice
        self.orientation_map[y, x] = None
        self.occupancy_map[y, x] = False

    def _populate(self, density: float) -> int:
        """
        Initialize the lattice with particles at a given density.

        :param density: Density of particles to be initialized.
        :return: The number of particles added to the lattice.
        """
        num_cells = self.width * self.height - self.obstacles.sum().item()
        num_cells = int(num_cells)
        num_particles = int(density * num_cells)

        # Generate random orientations using the Orientation enum
        positions = torch.randperm(num_cells, generator=self.generator)[:num_particles]

        n_added = 0

        for pos in positions:
            y, x = divmod(
                pos.item(), self.width
            )  # Convert position to (x, y) coordinates
            while self._is_obstacle(x, y) or not self._is_empty(x, y):
                pos = torch.randint(
                    num_cells, (1,), device=device, generator=self.generator
                ).item()
                y, x = divmod(pos, self.width)
            self.add_particle(x, y)
            n_added += 1
        return n_added

    def add_particle_flux(
        self,
        region: Tuple[int, int, int, int],
        orientation: Orientation,
        n_particles: int,
    ) -> int:
        """
        Add a particle flux to the lattice.

        :param region: A tuple of (x1, y1, x2, y2) representing the region where particles will be added.
        :param orientation: The orientation of the particles.
        :param n_particles: The number of particles to be added.
        :return: The number of particles added to the lattice.
        """
        x1, x2, y1, y2 = region
        if x1 < 0 or y1 < 0 or x2 >= self.width or y2 >= self.height:
            raise ValueError(f"Region coordinates {region} are out of lattice bounds.")

        n_added = 0
        region_area = (x2 - x1 + 1) * (y2 - y1 + 1)
        positions = np.random.choice(region_area, n_particles, replace=False)

        for pos in positions:
            y, x = divmod(pos, x2 - x1 + 1)
            x, y = x + x1, y + y1
            while self._is_obstacle(x, y) or not self._is_empty(x, y):
                pos = np.random.choice(region_area)
                y, x = divmod(pos, x2 - x1 + 1)
                x, y = x + x1, y + y1
            self.add_particle(x, y, orientation)

            n_added += 1
        return n_added

    def get_particle_orientation(self, x: int, y: int) -> Orientation:
        """
        Get the orientation of a particle at (x, y).

        :param x: x-coordinate of the particle.
        :param y: y-coordinate of the particle.
        :return: The orientation of the particle as an Orientation enum instance. None if no particle is found.
        """
        self._validate_occupancy(x, y)
        delta_to_orientation = {
            (0, -1): Orientation.UP,
            (0, 1): Orientation.DOWN,
            (-1, 0): Orientation.LEFT,
            (1, 0): Orientation.RIGHT,
            (0, 0): Orientation.EMPTY,
        }
        return delta_to_orientation[tuple(self.particles[y, x].numpy())]

    def move_particle(self, x: int, y: int) -> None:
        """
        Move a particle at (x, y) with a given orientation to the new position determined by its current orientation.
        :param x: Current x-coordinate of the particle.
        :param y: Current y-coordinate of the particle.
        :return: A list of tuples representing the new position of the particle.
        :raises ValueError: If no particle is found at the given location.
        """

        self._validate_occupancy(
            x, y
        )  # Check if the particle exists at the given location
        orientation = self.get_particle_orientation(x, y)
        # Get the expected position of the particle
        new_x, new_y = self._get_target_position(x, y, orientation)

        if self._is_obstacle(new_x, new_y):
            new_x, new_y = x, y
            new_orientation = Orientation((orientation.value + 2) % 4)
            self.reorient_particle(x, y, new_orientation)
            return [new_x, new_y]

        particle_id = self.position_to_particle_id.pop((x, y))
        self._update_tracking(particle_id, new_x, new_y)

        if self._is_sink(new_x, new_y):
            self.remove_particle(x, y)
            return []

        # Directly update the particle's position in the lattice
        self.particles[new_y, new_x] = self.particles[y, x]
        self.particles[y, x] = 0

        # Update the orientation map
        self.orientation_map[y, x] = None
        self.orientation_map[new_y, new_x] = orientation
        # Update the occupancy map
        self.occupancy_map[y, x] = False
        self.occupancy_map[new_y, new_x] = True

        return [(new_x, new_y)]

    def transport_particle(self, x: int, y: int, direction: Orientation) -> List[tuple]:
        """
        Move a particle at (x, y) with a given orientation to the new position determined by the prescribed orientation.
        :param x: Current x-coordinate of the particle.
        :param y: Current y-coordinate of the particle.
        :return: A list of tuples representing the new position of the particle.
        :raises ValueError: If no particle is found at the given location.
        """

        self._validate_occupancy(
            x, y
        )  # Check if the particle exists at the given location

        # Get the expected position of the particle, and the old orientation
        new_x, new_y = self._get_target_position(x, y, direction)
        if self._is_obstacle(new_x, new_y):
            return []
        orientation = self.get_particle_orientation(x, y)

        # get the id of the particle at (x, y)
        particle_id = self.position_to_particle_id.pop((x, y), None)
        self._update_tracking(particle_id, new_x, new_y)
        if self._is_sink(new_x, new_y):
            self.remove_particle(x, y)
            return []

        self.particles[new_y, new_x] = self.particles[y, x]
        self.particles[y, x] = 0
        return [(new_x, new_y)]

    def reorient_particle(self, x: int, y: int, new_orientation: Orientation) -> bool:
        """
        Reorient a particle at (x, y) to a new orientation.

        :param x: x-coordinate of the particle.
        :param y: y-coordinate of the particle.
        :param new_orientation: The new orientation for the particle as an Orientation enum instance.
        :return: True if the particle was reoriented successfully, False otherwise.
        """
        # Validate that new_orientation is an instance of Orientation
        if not isinstance(new_orientation, Orientation):
            raise ValueError(
                f"{new_orientation=} must be an instance of Orientation enum."
            )

        # Update the orientation in the particles tensor and orientation_map
        self.particles[y, x] = torch.tensor(self.orientation_deltas[new_orientation])
        self.orientation_map[y, x] = new_orientation

    def rotate(self, x: int, y: int, cw: bool=True) -> None:
        """
        Rotate the orientation of a particle at a given location CCW or CW.
        :param x: x-coordinate of the particle.
        :param y: y-coordinate of the particle.
        :param cw: If True, rotate the particle CW, otherwise rotate CCW.
        """
        R = -(2 * cw - 1) * torch.tensor([[0, 1], [-1, 0]], dtype=torch.int8)

        self.particles[y, x] = torch.matmul(R, self.particles[y, x])
    
    def flip(self, x: int, y: int) -> None:
        """
        Flip the orientation of a particle at a given position.
        :param x: x-coordinate of the particle.
        :param y: y-coordinate of the particle.
        """
        self.particles[y, x] = -self.particles[y, x]

    def compute_rotated_particles(self, cw: bool=True, mask: Optional[torch.Tensor]=None) -> torch.Tensor:
        """
        Compute the rotated particles for a given mask.
        :param cw: If True, rotate the particles CW, otherwise rotate CCW.
        :param mask: A binary mask indicating the particles to rotate.
        :return: The rotated particles.
        """
        R = (2 * cw - 1) * torch.tensor([[0, 1], [-1, 0]], dtype=torch.int8)
        rotated_particles = torch.matmul(self.particles, R)
        if mask is not None:
            rotated_particles = rotated_particles * mask.unsqueeze(-1) + self.particles * (~mask).unsqueeze(-1)

        return rotated_particles
    
    def rotate_particles(self, cw: bool=True, mask: Optional[torch.Tensor]=None) -> None:
        """
        Rotate the particles in the lattice.
        :param cw: If True, rotate the particles CW, otherwise rotate CCW.
        :param mask: A binary mask indicating the particles to rotate.
        """
        self.particles = self.compute_rotated_particles(cw, mask)


    ##################################
    ## Obstacle and sink management ##
    ##################################

    def set_obstacle(self, x: int, y: int) -> None:
        """
        Set an obstacle at the specified position in the lattice,
        provided the cell is empty and not already an obstacle or a sink.

        Parameters:
        x (int): The x-coordinate of the position.
        y (int): The y-coordinate of the position.

        Raises:
        ValueError: If the specified position is outside the lattice bounds or already occupied.
        """
        self._validate_coordinates(x, y)
        self._validate_availability(x, y)

        self.obstacles[y, x] = True

    def set_sink(self, x: int, y: int) -> None:
        """
        Set a sink at the specified position in the lattice,
        provided the cell is empty and not already an obstacle or a sink.

        Parameters:
        x (int): The x-coordinate of the position.
        y (int): The y-coordinate of the position.

        Raises:
        ValueError: If the specified position is outside the lattice bounds or already occupied.
        """
        self._validate_coordinates(x, y)
        self._validate_availability(x, y)
        self.sinks[y, x] = True

    def set_obstacles(self, obstacles: torch.Tensor) -> None:
        """
        Set the obstacles for the lattice.
        :param obstacles: A binary matrix indicating the obstacle cells.
        """
        if obstacles.shape != (self.height, self.width):
            raise ValueError(
                f"Obstacles tensor must match the lattice dimensions. \n >>> {obstacles.shape=}, {(self.height, self.width)=}"
            )
        self.obstacles = obstacles

    def set_sinks(self, sinks: torch.Tensor) -> None:
        """
        Set the sinks for the lattice.
        :param sinks: A binary matrix indicating the sink cells.
        """
        if sinks.shape != (self.height, self.width):
            raise ValueError("Sinks tensor must match the lattice dimensions.")
        self.sinks = sinks

    def set_sources(self, sources: torch.Tensor) -> None:
        """
        Set the sources for the lattice.
        :param sources: A binary matrix indicating the source cells.
        """
        if sources.shape != (self.height, self.width):
            raise ValueError("Sources tensor must match the lattice dimensions.")
        self.sources = sources
        # zero out the sources for obstacle cells
        self.sources = self.sources * ~self.obstacles

    ##################################
    ## State Querying and Reporting ##
    ##################################

    def query_lattice_state(self) -> torch.Tensor:
        """
        Query the current state of the lattice.

        :return: The state of the lattice.
        """
        return self.particles

    ###################################
    ## String Representation Methods ##
    ###################################

    def __str__(self) -> str:
        """
        String representation of the lattice.
        :return: A string representation of the lattice.
        """
        index_to_symbol = self._create_index_to_symbol_mapping()
        obstacle_symbol = "■"  # Symbol for obstacles
        sink_symbol = "▼"  # Symbol for sinks
        particle_in_sink_symbol = "✱"  # Symbol for particle in a sink
        lattice_str = ""

        for y in range(self.height):
            row_str = ""
            for x in range(self.width):
                if self.obstacles[y, x]:
                    row_str += obstacle_symbol
                elif self.sinks[y, x]:
                    if not self._is_empty(x, y):  # Check for particle in sink
                        row_str += particle_in_sink_symbol
                    else:
                        row_str += sink_symbol
                elif self._is_empty(x, y):
                    row_str += "·"  # Use a dot for empty cells
                else:
                    orientation_index = self.get_particle_orientation(x, y).value
                    symbol = index_to_symbol[orientation_index]
                    row_str += symbol
                row_str += " "  # Add space between cells
            lattice_str += row_str
            if y < self.height - 1:
                lattice_str += (
                    "\n"  # Add a newline character after each row except the last
                )

        return lattice_str

    def __repr__(self) -> str:
        """
        Representation of the lattice.
        :return: A string representation of the lattice.
        """
        return self.__str__()

    def __getitem__(self, key):
        """
        Enables slicing of the ParticleLattice and validates the slicing keys.

        :param key: The slicing key.
        :return: A new ParticleLattice instance with the sliced data.
        """
        # Validate and adjust the slicing keys
        if not isinstance(key, tuple) or len(key) != 2:
            raise ValueError("Slicing key must be a tuple of two slice objects.")

        key_y, key_x = key
        key_y = slice(
            max(0, key_y.start or 0),
            min(self.height, key_y.stop or self.height),
            key_y.step,
        )
        key_x = slice(
            max(0, key_x.start or 0),
            min(self.width, key_x.stop or self.width),
            key_x.step,
        )
        adjusted_key = (key_y, key_x)

        # Create a new instance of ParticleLattice
        new_lattice = ParticleLattice(self.width, self.height, mode=self.mode)

        # Slicing the tensors
        new_lattice.particles = self.particles[:, adjusted_key[0], adjusted_key[1]]
        new_lattice.obstacles = self.obstacles[adjusted_key[0], adjusted_key[1]]
        new_lattice.sinks = self.sinks[adjusted_key[0], adjusted_key[1]]

        # Update the width and height of the new lattice
        new_lattice.width = new_lattice.obstacles.shape[1]
        new_lattice.height = new_lattice.obstacles.shape[0]

        # Resetting other attributes
        new_lattice.id_to_position = {}
        new_lattice.position_to_particle_id = {}
        new_lattice.next_particle_id = 0

        return new_lattice

    def copy(self):
        return copy.deepcopy(self)

    def visualize_lattice(self):
        lattice_str = ""
        index_to_symbol = self._create_index_to_symbol_mapping()
        orientation_to_color = {
            0: "red",
            1: "green",
            2: "blue",
            3: "yellow",
            # Add more mappings as needed
        }

        for y in range(self.height):
            row_str = ""
            for x in range(self.width):
                if self.obstacles[y, x]:
                    cell_str = "[bold white]■[/]"  # Obstacle
                elif self.sinks[y, x]:
                    if not self._is_empty(x, y):
                        cell_str = "[bold cyan]✱[/]"  # Particle in sink
                    else:
                        cell_str = "[bold magenta]▼[/]"  # Sink
                elif self._is_empty(x, y):
                    cell_str = "[dim]·[/]"  # Empty cell
                else:
                    orientation_index = self.get_particle_orientation(x, y).value
                    color = orientation_to_color.get(orientation_index, "white")
                    symbol = index_to_symbol[orientation_index]
                    cell_str = f"[bold {color}]{symbol}[/]"
                row_str += cell_str + " "
            lattice_str += row_str.strip() + "\n"

        return lattice_str.strip()
