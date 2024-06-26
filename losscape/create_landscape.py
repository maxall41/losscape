import torch

import math
import numpy as np
from scipy import interpolate
import matplotlib.pyplot as plt
import h5py
import os

from losscape.compute_loss import compute_loss
from losscape.create_directions import create_random_direction, create_random_directions

#todo : plot anim la traj d'une optim avec PCA
#todo : losscape avec le test loss
#todo pour la lib : possiblité de tout foutre dans un fichier, et il fait les exps automatiquement ? (genre on met model + dataloader + optim + loss et il loop sur les models + optims)

device = "cuda" if torch.cuda.is_available() else "cpu"

def create_2D_losscape(model, train_loader_unshuffled=None, get_batch=None, direction=None, criterion = None, closure = None, num_batches:int = 8, save_only:bool = False, output_path:str = '', x_min:float=-1., x_max:float=1., num_points:int=50):
    """
    Create a 2D losscape of the given model.

    Parameters
    ----------
    model : the torch model which will be used to create the losscape.
    train_loader_unshuffled : the torch dataloader. It is supposed to be fixed so that all the calls to this function will use the same data.
    optimizer : the optimizer used for training (should follow the same API as torch optimizers).(default to Adam)
    criterion : the criterion used to compute the loss. (default to F.cross_entropy)
    closure : an optional closure that will replace the default compute_loss internals
    num_batches : number of batches to evaluate the model with. (default to 8)
    save_only : only save the plot and don't display it. (default to False)
    output_path : path where the plot will be saved. (default to '2d_losscape.png')
    x_min : min x value (that multiply the sampled direction). (default to -1.) 
    x_max : max x value (that multiply the sampled direction). (default to 1.)
    num_points : number of points to evaluate the loss, from x_min to x_max. (default to 50)

    Returns
    ----------
    coords : numpy array containing the x coords used to create the landscape
    losses : list of the losses computed

    """

    model.to(device)

    if direction is None:
        direction = [create_random_direction(model)]

    init_weights = [p.data for p in model.parameters()]

    coords = np.linspace(x_min, x_max, num_points)
    losses = []

    for x in coords:
        _set_weights(model, init_weights, direction, x)

        loss = compute_loss(model, train_loader_unshuffled, get_batch, criterion, num_batches, closure = closure)
        losses.append(loss)

    _reset_weights(model, init_weights)
    
    plt.plot(coords, losses)
    plt.savefig(os.path.join(output_path, '2d_losscape.png'), dpi=300)

    if not save_only:
        plt.show()
    
    plt.clf()

    return coords, losses

def create_3D_losscape(model, train_loader_unshuffled=None, get_batch=None, directions=None, criterion = None, closure = None, num_batches:int = 8, save_only:bool = False, output_path:str = '', output_vtp:bool = True, output_h5:bool = True, x_min:float=-1., x_max:float=1., y_min:float=-1., y_max:float=1., num_points:int=50):
    """
    Create a 3D losscape of the given model.

    Parameters
    ----------
    model : the torch model which will be used to create the losscape.
    train_loader_unshuffled : the torch dataloader. It is supposed to be fixed so that all the calls to this function will use the same data.
    optimizer : the optimizer used for training (should follow the same API as torch optimizers).(default to Adam)
    criterion : the criterion used to compute the loss. (default to F.cross_entropy)
    closure : an optional closure that will replace the default compute_loss internals
    num_batches : number of batches to evaluate the model with. (default to 8)
    save_only : only save the plot and don't display it. (default to False)
    output_path : path where the plot will be saved. (default to '3d_losscape.png')
    output_vpt : whether or not to also create a .vtp file, used to 3D visualize the losscape. (default to False)
    output_h5 : whether or not to also create a .h5 file, containing the data generated by this function (default to True)
    x_min : min x value (that multiply the first sampled direction). (default to -1.) 
    x_max : max x value (that multiply the first sampled direction). (default to 1.)
    y_min : min x value (that multiply the second sampled direction). (default to -1.) 
    y_max : max x value (that multiply the second sampled direction). (default to 1.)
    num_points : number of points to evaluate the loss, from x_min to x_max and y_min to y_max. (default to 50)

    Returns
    ----------
    X : a (num_points, num_points) numpy array, the X meshgrid
    Y : a (num_points, num_points) numpy array, the Y meshgrid
    losses : a (num_points, num_points) numpy array containing all the losses computed

    Notes
    ----------
    The h5 files is structured as follows :

    """

    model.to(device)

    if directions is None:
        directions = create_random_directions(model)

    init_weights = [p.data for p in model.parameters()]

    X, Y = np.meshgrid(np.linspace(x_min, x_max, num_points), np.linspace(y_min, y_max, num_points))
    losses = np.empty_like(X)

    count = 0
    total = X.shape[0] * X.shape[1]

    for i in range(X.shape[0]):
        for j in range(X.shape[1]):
            _set_weights(model, init_weights, directions, np.array([X[i, j], Y[i, j]]))

            loss = compute_loss(model, train_loader_unshuffled, get_batch, criterion, num_batches, closure = closure)
            losses[i, j] = loss

            count += 1
            print("LOSS FOR x={} AND y={} IS : {}. Done : {}/{} ({}%)".format(X[i, j], Y[i, j], loss, count, total, count/total*100.))

    _reset_weights(model, init_weights)

    cp = plt.contour(X, Y, losses, cmap='summer')
    plt.clabel(cp, inline=1, fontsize=8)
    plt.savefig(os.path.join(output_path, '3d_losscape.png'), dpi=300)
    
    if not save_only:
        plt.show()
    
    plt.clf()

    if output_vtp:
        _create_vtp(X, Y, losses, log=True, output_path=output_path)
        _create_vtp(X, Y, losses, log=False, output_path=output_path)

    if output_h5:
        with h5py.File(os.path.join(output_path, 'data.h5'), 'w') as hf:
            hf.create_dataset("X", data=X)
            hf.create_dataset("Y", data=Y)
            hf.create_dataset("losses", data=losses)

    return X, Y, losses

def _set_weights(model, weights, directions, step):
    if len(directions) == 2:
        dx = directions[0]
        dy = directions[1]
        changes = [d0*step[0] + d1*step[1] for (d0, d1) in zip(dx, dy)]

    else:
        changes = [d*step for d in directions[0]]

    for (p, w, d) in zip(model.parameters(), weights, changes):
        p.data = w + d

def _reset_weights(model, weights):
    for (p, w) in zip(model.parameters(), weights):
        p.data.copy_(w.type(type(p.data)))

# as in https://github.com/tomgoldstein/loss-landscape
def _create_vtp(X, Y, losses, log=False, zmax=-1, interp=-1, output_path=''):
    #set this to True to generate points
    show_points = False
    #set this to True to generate polygons
    show_polys = True

    xcoordinates = X
    ycoordinates = Y
    vals = losses

    x_array = xcoordinates[:].ravel()
    y_array = ycoordinates[:].ravel()
    z_array = vals[:].ravel()

    # Interpolate the resolution up to the desired amount
    if interp > 0:
        m = interpolate.interp2d(xcoordinates[0,:], ycoordinates[:,0], vals, kind='cubic')
        x_array = np.linspace(min(x_array), max(x_array), interp)
        y_array = np.linspace(min(y_array), max(y_array), interp)
        z_array = m(x_array, y_array).ravel()

        x_array, y_array = np.meshgrid(x_array, y_array)
        x_array = x_array.ravel()
        y_array = y_array.ravel()

    vtp_file = os.path.join(output_path, 'losscape')
    if zmax > 0:
        z_array[z_array > zmax] = zmax
        vtp_file +=  "_zmax=" + str(zmax)

    if log:
        z_array = np.log(z_array + 0.1)
        vtp_file +=  "_log"
    vtp_file +=  ".vtp"
    print("Here's your output file:{}".format(vtp_file))

    number_points = len(z_array)
    print("number_points = {} points".format(number_points))

    matrix_size = int(math.sqrt(number_points))
    print("matrix_size = {} x {}".format(matrix_size, matrix_size))

    poly_size = matrix_size - 1
    print("poly_size = {} x {}".format(poly_size, poly_size))

    number_polys = poly_size * poly_size
    print("number_polys = {}".format(number_polys))

    min_value_array = [min(x_array), min(y_array), min(z_array)]
    max_value_array = [max(x_array), max(y_array), max(z_array)]
    min_value = min(min_value_array)
    max_value = max(max_value_array)

    averaged_z_value_array = []

    poly_count = 0
    for column_count in range(poly_size):
        stride_value = column_count * matrix_size
        for row_count in range(poly_size):
            temp_index = stride_value + row_count
            averaged_z_value = (z_array[temp_index] + z_array[temp_index + 1] +
                                z_array[temp_index + matrix_size]  +
                                z_array[temp_index + matrix_size + 1]) / 4.0
            averaged_z_value_array.append(averaged_z_value)
            poly_count += 1

    avg_min_value = min(averaged_z_value_array)
    avg_max_value = max(averaged_z_value_array)

    output_file = open(vtp_file, 'w')
    output_file.write('<VTKFile type="PolyData" version="1.0" byte_order="LittleEndian" header_type="UInt64">\n')
    output_file.write('  <PolyData>\n')

    if (show_points and show_polys):
        output_file.write('    <Piece NumberOfPoints="{}" NumberOfVerts="{}" NumberOfLines="0" NumberOfStrips="0" NumberOfPolys="{}">\n'.format(number_points, number_points, number_polys))
    elif (show_polys):
        output_file.write('    <Piece NumberOfPoints="{}" NumberOfVerts="0" NumberOfLines="0" NumberOfStrips="0" NumberOfPolys="{}">\n'.format(number_points, number_polys))
    else:
        output_file.write('    <Piece NumberOfPoints="{}" NumberOfVerts="{}" NumberOfLines="0" NumberOfStrips="0" NumberOfPolys="">\n'.format(number_points, number_points))

    # <PointData>
    output_file.write('      <PointData>\n')
    output_file.write('        <DataArray type="Float32" Name="zvalue" NumberOfComponents="1" format="ascii" RangeMin="{}" RangeMax="{}">\n'.format(min_value_array[2], max_value_array[2]))
    for vertexcount in range(number_points):
        if (vertexcount % 6) == 0:
            output_file.write('          ')
        output_file.write('{}'.format(z_array[vertexcount]))
        if (vertexcount % 6) == 5:
            output_file.write('\n')
        else:
            output_file.write(' ')
    if (vertexcount % 6) != 5:
        output_file.write('\n')
    output_file.write('        </DataArray>\n')
    output_file.write('      </PointData>\n')

    # <CellData>
    output_file.write('      <CellData>\n')
    if (show_polys and not show_points):
        output_file.write('        <DataArray type="Float32" Name="averaged zvalue" NumberOfComponents="1" format="ascii" RangeMin="{}" RangeMax="{}">\n'.format(avg_min_value, avg_max_value))
        for vertexcount in range(number_polys):
            if (vertexcount % 6) == 0:
                output_file.write('          ')
            output_file.write('{}'.format(averaged_z_value_array[vertexcount]))
            if (vertexcount % 6) == 5:
                output_file.write('\n')
            else:
                output_file.write(' ')
        if (vertexcount % 6) != 5:
            output_file.write('\n')
        output_file.write('        </DataArray>\n')
    output_file.write('      </CellData>\n')

    # <Points>
    output_file.write('      <Points>\n')
    output_file.write('        <DataArray type="Float32" Name="Points" NumberOfComponents="3" format="ascii" RangeMin="{}" RangeMax="{}">\n'.format(min_value, max_value))
    for vertexcount in range(number_points):
        if (vertexcount % 2) == 0:
            output_file.write('          ')
        output_file.write('{} {} {}'.format(x_array[vertexcount], y_array[vertexcount], z_array[vertexcount]))
        if (vertexcount % 2) == 1:
            output_file.write('\n')
        else:
            output_file.write(' ')
    if (vertexcount % 2) != 1:
        output_file.write('\n')
    output_file.write('        </DataArray>\n')
    output_file.write('      </Points>\n')

    # <Verts>
    output_file.write('      <Verts>\n')
    output_file.write('        <DataArray type="Int64" Name="connectivity" format="ascii" RangeMin="0" RangeMax="{}">\n'.format(number_points - 1))
    if (show_points):
        for vertexcount in range(number_points):
            if (vertexcount % 6) == 0:
                output_file.write('          ')
            output_file.write('{}'.format(vertexcount))
            if (vertexcount % 6) == 5:
                output_file.write('\n')
            else:
                output_file.write(' ')
        if (vertexcount % 6) != 5:
            output_file.write('\n')
    output_file.write('        </DataArray>\n')
    output_file.write('        <DataArray type="Int64" Name="offsets" format="ascii" RangeMin="1" RangeMax="{}">\n'.format(number_points))
    if (show_points):
        for vertexcount in range(number_points):
            if (vertexcount % 6) == 0:
                output_file.write('          ')
            output_file.write('{}'.format(vertexcount + 1))
            if (vertexcount % 6) == 5:
                output_file.write('\n')
            else:
                output_file.write(' ')
        if (vertexcount % 6) != 5:
            output_file.write('\n')
    output_file.write('        </DataArray>\n')
    output_file.write('      </Verts>\n')

    # <Lines>
    output_file.write('      <Lines>\n')
    output_file.write('        <DataArray type="Int64" Name="connectivity" format="ascii" RangeMin="0" RangeMax="{}">\n'.format(number_polys - 1))
    output_file.write('        </DataArray>\n')
    output_file.write('        <DataArray type="Int64" Name="offsets" format="ascii" RangeMin="1" RangeMax="{}">\n'.format(number_polys))
    output_file.write('        </DataArray>\n')
    output_file.write('      </Lines>\n')

    # <Strips>
    output_file.write('      <Strips>\n')
    output_file.write('        <DataArray type="Int64" Name="connectivity" format="ascii" RangeMin="0" RangeMax="{}">\n'.format(number_polys - 1))
    output_file.write('        </DataArray>\n')
    output_file.write('        <DataArray type="Int64" Name="offsets" format="ascii" RangeMin="1" RangeMax="{}">\n'.format(number_polys))
    output_file.write('        </DataArray>\n')
    output_file.write('      </Strips>\n')

    # <Polys>
    output_file.write('      <Polys>\n')
    output_file.write('        <DataArray type="Int64" Name="connectivity" format="ascii" RangeMin="0" RangeMax="{}">\n'.format(number_polys - 1))
    if (show_polys):
        polycount = 0
        for column_count in range(poly_size):
            stride_value = column_count * matrix_size
            for row_count in range(poly_size):
                temp_index = stride_value + row_count
                if (polycount % 2) == 0:
                    output_file.write('          ')
                output_file.write('{} {} {} {}'.format(temp_index, (temp_index + 1), (temp_index + matrix_size + 1), (temp_index + matrix_size)))
                if (polycount % 2) == 1:
                    output_file.write('\n')
                else:
                    output_file.write(' ')
                polycount += 1
        if (polycount % 2) == 1:
            output_file.write('\n')
    output_file.write('        </DataArray>\n')
    output_file.write('        <DataArray type="Int64" Name="offsets" format="ascii" RangeMin="1" RangeMax="{}">\n'.format(number_polys))
    if (show_polys):
        for polycount in range(number_polys):
            if (polycount % 6) == 0:
                output_file.write('          ')
            output_file.write('{}'.format((polycount + 1) * 4))
            if (polycount % 6) == 5:
                output_file.write('\n')
            else:
                output_file.write(' ')
        if (polycount % 6) != 5:
            output_file.write('\n')
    output_file.write('        </DataArray>\n')
    output_file.write('      </Polys>\n')

    output_file.write('    </Piece>\n')
    output_file.write('  </PolyData>\n')
    output_file.write('</VTKFile>\n')
    output_file.write('')
    output_file.close()

    print("Done with file:{}".format(vtp_file))
