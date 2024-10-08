import pytest
from lvmc.core.lattice import ParticleLattice, Orientation
import torch
import numpy as np


def test_particle_lattice_initialization():
    width, height = 10, 10
    lattice = ParticleLattice(width, height)

    assert lattice.width == width
    assert lattice.height == height


def test_set_obstacle_success():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    lattice.set_obstacle(x, y)
    assert lattice.obstacles[y, x] == True


def test_set_sink_success():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 3, 3
    lattice.set_sink(x, y)
    assert lattice._is_sink(x, y) == True


def test_set_obstacle_on_occupied_cell():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 4, 4
    lattice.add_particle(x, y, Orientation.UP)  # Add a particle

    # Attempt to set an obstacle on the same spot
    with pytest.raises(ValueError):
        lattice.set_obstacle(x, y)


def test_set_sink_on_obstacle():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    lattice.set_obstacle(x, y)  # Set an obstacle

    # Attempt to set a sink on the same spot
    with pytest.raises(ValueError):
        lattice.set_sink(x, y)


def test_set_sink_on_occupied_cell():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 6, 6
    lattice.add_particle(x, y, Orientation.UP)  # Set a sink

    # Attempt to set sink on the same spot
    with pytest.raises(ValueError):
        lattice.set_sink(x, y)


def test_set_obstacle_outside_bounds():
    lattice = ParticleLattice(width=10, height=10)
    # Coordinates outside the lattice bounds
    x, y = 11, 11
    with pytest.raises(IndexError):
        lattice.set_obstacle(x, y)


def test_set_sink_outside_bounds():
    lattice = ParticleLattice(width=10, height=10)
    # Coordinates outside the lattice bounds
    x, y = 11, 11
    with pytest.raises(IndexError):
        lattice.set_sink(x, y)


def test_populate():
    lattice = ParticleLattice(width=10, height=10)
    density = 0.5
    lattice.populate(density)
    populated_cells = lattice.n_particles
    expected_cells = int(density * lattice.width * lattice.height)
    assert populated_cells == expected_cells
    # add test for obstacles and sinks


def test__is_empty():
    lattice = ParticleLattice(width=10, height=10)
    assert lattice._is_empty(5, 5) == True
    lattice.add_particle(5, 5, Orientation.UP)
    assert lattice._is_empty(5, 5) == False


def test_add_particle():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    orientation = Orientation.UP  # Changed to use Orientation enum
    lattice.add_particle(x, y, orientation)
    assert lattice._is_empty(x, y) == False


def test_add_particle_outside_bounds():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 11, 11
    orientation = Orientation.UP
    with pytest.raises(IndexError):
        lattice.add_particle(x, y, orientation)


def test_add_particle_on_obstacle():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    lattice.set_obstacle(x, y)
    orientation = Orientation.UP
    with pytest.raises(ValueError):
        lattice.add_particle(x, y, orientation)


def test_add_particle_on_sink():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    lattice.set_sink(x, y)
    orientation = Orientation.UP
    # the particle should still be added
    lattice.add_particle(x, y, orientation)
    assert lattice.get_particle_orientation(x, y) == orientation
    assert lattice._is_sink(x, y) == True
    assert lattice._is_empty(x, y) == False


def test_add_particle_on_occupied_cell():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    orientation = Orientation.UP
    lattice.add_particle(x, y, orientation)

    with pytest.raises(ValueError):
        lattice.add_particle(x, y, orientation)


def test_remove_particle():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    orientation = Orientation.UP
    lattice.add_particle(x, y, orientation)
    lattice.remove_particle(x, y)
    assert lattice._is_empty(x, y) == True


def test_remove_particle_outside_bounds():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 11, 11
    with pytest.raises(IndexError):
        lattice.remove_particle(x, y)


def test_get_target_position():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5

    # Add a particle to the lattice in the cell (x,y)
    orientation = np.random.choice(list(Orientation))
    lattice.add_particle(x, y, orientation)

    # Check if the target position is correct for each orientation
    # 1. Up
    assert lattice._get_target_position(x, y, Orientation.UP) == (
        x,
        (y - 1) % lattice.height,
    )
    # 2. Down
    assert lattice._get_target_position(x, y, Orientation.DOWN) == (
        x,
        (y + 1) % lattice.height,
    )
    # 3. Left
    assert lattice._get_target_position(x, y, Orientation.LEFT) == (
        (x - 1) % lattice.width,
        y,
    )
    # 4. Right
    assert lattice._get_target_position(x, y, Orientation.RIGHT) == (
        (x + 1) % lattice.width,
        y,
    )


def test__is_obstacle():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    lattice.set_obstacle(x, y)
    assert lattice._is_obstacle(x, y)

    # Check if the method returns False for non-obstacle cells
    assert not lattice._is_obstacle(0, 0)
    assert not lattice._is_obstacle(1, 1)
    assert not lattice._is_obstacle(2, 2)


def test__is_sink():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    lattice.set_sink(x, y)
    assert lattice._is_sink(x, y)

    # Check if the method returns False for non-sink cells
    assert not lattice._is_sink(0, 0)
    assert not lattice._is_sink(1, 1)
    assert not lattice._is_sink(2, 2)


def test__is_sink_with_obstacles():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    lattice.set_sink(x, y)
    lattice.set_obstacle(x + 1, y)
    assert lattice._is_sink(x, y)

    # Check if the method returns False for non-sink cells
    assert not lattice._is_sink(0, 0)
    assert not lattice._is_sink(1, 1)
    assert not lattice._is_sink(2, 2)


def test__is_sink_with_particles():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    orientation = Orientation.UP
    lattice.set_sink(x, y)
    lattice.add_particle(x, y, orientation)

    assert lattice._is_sink(x, y)

    # Check if the method returns False for non-sink cells
    assert not lattice._is_sink(0, 0)
    assert not lattice._is_sink(1, 1)
    assert not lattice._is_sink(2, 2)


def test_get_particle_orientation():
    lattice = ParticleLattice(width=10, height=10)
    x, y = np.random.randint(0, lattice.width), np.random.randint(0, lattice.height)
    orientation = Orientation(np.random.randint(0, len(Orientation)))
    lattice.add_particle(x, y, orientation)
    assert lattice.get_particle_orientation(x, y) == orientation


def test_get_particle_orientation_outside_bounds():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 11, 11
    with pytest.raises(IndexError):
        lattice.get_particle_orientation(x, y)


def test_get_particle_orientation_on_empty_cell():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    with pytest.raises(ValueError):
        lattice.get_particle_orientation(x, y)


def test_get_particle_orientation_on_obstacle():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    lattice.set_obstacle(x, y)
    with pytest.raises(ValueError):
        lattice.get_particle_orientation(x, y)


def test_get_particle_orientation_on_sink():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    lattice.set_sink(x, y)

    # If no particle is on the sink, it should raise an error
    with pytest.raises(ValueError):
        lattice.get_particle_orientation(x, y)

    # If a particle is on the sink, it should return the orientation of the particle
    orientation = np.random.choice(list(Orientation))
    lattice.add_particle(x, y, orientation)
    assert lattice.get_particle_orientation(x, y) == orientation


def test_get_particle_orientation_on_sink_with_obstacles():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    lattice.set_sink(x, y)
    lattice.set_obstacle(x + 1, y)

    # If no particle is on the sink, it should raise an error
    with pytest.raises(ValueError):
        lattice.get_particle_orientation(x, y)

    # If a particle is on the sink, it should return the orientation of the particle
    orientation = np.random.choice(list(Orientation))
    lattice.add_particle(x, y, orientation)
    assert lattice.get_particle_orientation(x, y) == orientation


def test_move_particle():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    orientation = Orientation.UP
    lattice.add_particle(x, y, orientation)
    successful_move = lattice.move_particle(x, y)

    assert successful_move
    assert lattice._is_empty(x, y)
    assert not lattice._is_empty(x, (y - 1) % lattice.height)
    assert lattice.get_particle_orientation(x, (y - 1) % lattice.height) == orientation

    # Attempt to move a particle in an empty cell
    with pytest.raises(ValueError):
        lattice.move_particle(0, 0)


def test_move_particle_outside_bounds():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 11, 11
    with pytest.raises(IndexError):
        lattice.move_particle(x, y)


def test_move_particle_on_empty_cell():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    with pytest.raises(ValueError):
        lattice.move_particle(x, y)


def test_move_particle_on_obstacle():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    lattice.set_obstacle(x, y)
    with pytest.raises(ValueError):
        lattice.move_particle(x, y)


def test_move_particle_on_sink():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    lattice.set_sink(x, y)

    # If no particle is on the sink, it should raise an error
    with pytest.raises(ValueError):
        lattice.move_particle(x, y)

    # If a particle is on the sink, it should return the orientation of the particle
    orientation = np.random.choice(list(Orientation))
    lattice.add_particle(x, y, orientation)
    x_new, y_new = lattice._get_target_position(x, y, orientation)

    lattice.move_particle(x, y)
    assert lattice._is_empty(x, y)
    assert not lattice._is_empty(x_new, y_new)
    assert lattice.get_particle_orientation(x_new, y_new) == orientation


def test_move_particle_periodicity_up():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 0
    orientation = Orientation.UP
    lattice.add_particle(x, y, orientation)
    lattice.move_particle(x, y)

    assert lattice._is_empty(x, y)
    assert not lattice._is_empty(x, lattice.height - 1)
    assert lattice.get_particle_orientation(x, lattice.height - 1) == orientation


def test_move_particle_periodicity_down():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, lattice.height - 1
    orientation = Orientation.DOWN
    lattice.add_particle(x, y, orientation)
    lattice.move_particle(x, y)

    assert lattice._is_empty(x, y)
    assert not lattice._is_empty(x, 0)
    assert lattice.get_particle_orientation(x, 0) == orientation


def test_move_particle_periodicity_left():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 0, 5
    orientation = Orientation.LEFT
    lattice.add_particle(x, y, orientation)
    lattice.move_particle(x, y)

    assert lattice._is_empty(x, y)
    assert not lattice._is_empty(lattice.width - 1, y)
    assert lattice.get_particle_orientation(lattice.width - 1, y) == orientation


def test_move_particle_periodicity_right():
    lattice = ParticleLattice(width=10, height=10)
    x, y = lattice.width - 1, 5
    orientation = Orientation.RIGHT
    lattice.add_particle(x, y, orientation)
    lattice.move_particle(x, y)

    assert lattice._is_empty(x, y)
    assert not lattice._is_empty(0, y)
    assert lattice.get_particle_orientation(0, y) == orientation


def test_reorient_particle():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    original_orientation = Orientation(np.random.choice(list(Orientation)))
    lattice.add_particle(x, y, original_orientation)

    # Choose a new orientation different from the original
    new_orientations = list(set(Orientation) - {original_orientation})
    new_orientation = np.random.choice(new_orientations)

    lattice.reorient_particle(x, y, new_orientation)
    assert lattice.get_particle_orientation(x, y) == new_orientation

    # Check reorientation to the same orientation
    assert not lattice.reorient_particle(x, y, new_orientation)

    # Attempt to reorient a non-existent particle
    with pytest.raises(ValueError):
        lattice.reorient_particle(0, 0, Orientation.UP)


def test_transport_particle():
    lattice = ParticleLattice(width=10, height=10)
    x, y = 5, 5
    original_orientation = Orientation(np.random.choice(list(Orientation)))
    lattice.add_particle(x, y, original_orientation)

    # Choose a new orientation different from the original
    new_orientations = list(set(Orientation) - {original_orientation})
    direction = np.random.choice(new_orientations)

    # Get the target position
    x_new, y_new = lattice._get_target_position(x, y, direction)

    lattice.transport_particle(x, y, direction)
    assert lattice._is_empty(x, y)
    # Check that the new position is not empty

    assert not lattice._is_empty(x_new, y_new)

    # Check that the orientation of the particle is correct
    assert lattice.get_particle_orientation(x_new, y_new) == original_orientation


def test_reflective_boundary_conditions():
    lattice = ParticleLattice(width=10, height=10)
    lattice.add_particle(5, 5, Orientation.UP)
    lattice.set_obstacle(5, 4)
    lattice.move_particle(5, 5)

    lattice.add_particle(1, 2, Orientation.LEFT)
    lattice.set_obstacle(0, 2)
    lattice.move_particle(1, 2)

    lattice.add_particle(8, 8, Orientation.RIGHT)
    lattice.set_obstacle(9, 8)
    lattice.move_particle(8, 8)

    lattice.add_particle(5, 0, Orientation.DOWN)
    lattice.set_obstacle(5, 1)
    lattice.move_particle(5, 0)

    assert not lattice._is_empty(1, 2)
    assert not lattice._is_empty(8, 8)
    assert not lattice._is_empty(5, 0)
    assert not lattice._is_empty(5, 5)

    assert lattice.get_particle_orientation(5, 5) == Orientation.DOWN
    assert lattice.get_particle_orientation(1, 2) == Orientation.RIGHT
    assert lattice.get_particle_orientation(8, 8) == Orientation.LEFT
    assert lattice.get_particle_orientation(5, 0) == Orientation.UP

    assert lattice._is_obstacle(5, 4)
    assert lattice._is_obstacle(0, 2)
    assert lattice._is_obstacle(9, 8)
    assert lattice._is_obstacle(5, 1)
