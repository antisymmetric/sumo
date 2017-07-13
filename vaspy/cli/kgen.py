#!/usr/bin/env python
# coding: utf-8
# Copyright (c) Scanlon Materials Theory Group
# Distributed under the terms of the MIT License.

from __future__ import unicode_literals

import os
import sys
import math
import shutil
import string
import logging
import argparse

import numpy as np

from vaspy.electronic_structure.bandstructure import (BradCrackKpath,
                                                      SeekpathKpath,
                                                      PymatgenKpath,
                                                      get_kpoints)

from pymatgen.io.vasp.inputs import Poscar, Kpoints

"""
A script to generate KPOINTS files for band structure calculations in VASP
"""

__author__ = "Alex Ganose"
__version__ = "1.0"
__maintainer__ = "Alex Ganose"
__email__ = "alexganose@googlemail.com"
__date__ = "July 6, 2017"

# TODO:
#  - sort padding value
#  - correct segment name
#  - correct file name if not splitting
#  - implement custom kpoint path


def kgen(filename, directory=None, make_folders=False, symprec=0.01,
         kpts_per_split=None, ibzkpt=None, spg=None, density=20,
         mode='bradcrack', cart_coords=False, kpt_list=None, labels=None):
    poscar = Poscar.from_file(filename)

    if spg and mode != 'brackcrack':
        logging.error("""ERROR: specifying symmetry only supported using Bradley
                      and Cracknell path""")
        sys.exit()

    if mode == 'bradcrack':
        kpath = BradCrackKpath(poscar.structure, symprec=symprec, spg=spg)
    elif mode == 'seekpath':
        kpath = SeekpathKpath(poscar.structure, symprec=symprec)
    elif mode == 'pymatgen':
        kpath = PymatgenKpath(poscar.structure, symprec=symprec)

    if kpt_list:
        kpoints, labels, path_str, kpt_dict = get_kpoints_from_list(
            poscar.structure, kpt_list, labels=labels, line_density=density,
            cart_coords=cart_coords)
    else:
        kpoints, labels = kpath.get_kpoints(line_density=density,
                                            cart_coords=cart_coords)
        path_str = kpath.path_string
        kpt_dict = kpath.kpoints

    logging.info('structure information:'.format(poscar.structure.num_sites))
    logging.info('\tspace group number: {}'.format(kpath._spg_data['number']))

    logging.info('\tinternational symbol: {}'.format(kpath.spg_symbol))
    logging.info('\tlattice type: {}'.format(kpath.lattice_type))
    # TODO: above won't work for pymatgen kpaths

    print_kpath_information(labels, path_str, kpt_dict)

    if not kpt_list and not np.allclose(poscar.structure.lattice.matrix,
                                        kpath.prim.lattice.matrix):
        prim_filename = '{}_prim'.format(os.path.basename(filename))
        kpath.prim.to(filename=prim_filename)

        logging.error("\nWARNING: the input structure does not match the "
                      "expected standard\nprimitive symmetry, the path may be "
                      "incorrect! Use at your own risk\n\nthe correct symmetry "
                      "primitive structure has been saved as {}".
                      format(prim_filename))

    if ibzkpt:
        try:
            ibzkpt = Kpoints.from_file('IBZKPT')
            if ibzkpt.tet_number != 0:
                logging.error('ERROR: IBZKPT contains tetrahedron information')
                sys.exit()
        except IOError:
            logging.error('ERROR: hybrid specified but no IBZKPT file found!')
            sys.exit()

    if make_folders and ibzkpt and not kpts_per_split:
        logging.info("""\nfound {} total kpoints in path, do you want to
                     split them up? (y/n)""".format(len(kpoints)))
        if raw_input()[0].lower() == 'y':
            logging.info("how many kpoints per file?")
            kpts_per_split = input()

    write_kpoint_files(filename, kpoints, labels, make_folders=make_folders,
                       ibzkpt=ibzkpt, kpts_per_split=kpts_per_split,
                       directory=directory, cart_coords=cart_coords)


def get_kpoints_from_list(structure, kpt_list, labels=None, line_density=20,
                          cart_coords=False):
    # TODO: do something smart here to get the repeat kpts right
    if not labels:
        labels = [s for s, x in zip(string.ascii_uppercase, kpt_list)]
    kpt_dict = dict(zip(labels, kpt_list))
    kpoints, labels = get_kpoints(structure, kpt_dict, labels,
                                  line_density=line_density,
                                  cart_coords=cart_coords)
    path_str = ' | '.join([' -> '.join(subpath) for subpath in labels])
    return kpoints, labels, path_str, kpt_dict


def print_kpath_information(labels, path_str, kpt_dict):
    logging.info('\nk-point path:\n\t{}'.format(path_str))
    logging.info('\nk-points:')
    for label, kpoint in kpt_dict.iteritems():
        coord_str = ' '.join(['{}'.format(c) for c in kpoint])
        logging.info('\t{}: {}'.format(label, coord_str))
    logging.info('\nk-point label indicies:')
    for i, label in enumerate(labels):
        if label:
            logging.info('\t{}: {}'.format(label, i+1))


def write_kpoint_files(filename, kpoints, labels, make_folders=False,
                       ibzkpt=None, kpts_per_split=None, directory=None,
                       cart_coords=False):
    if kpts_per_split:
        kpt_splits = [kpoints[i:i+kpts_per_split] for
                      i in xrange(0, len(kpoints), kpts_per_split)]
        label_splits = [labels[i:i+kpts_per_split] for
                        i in xrange(0, len(labels), kpts_per_split)]
    else:
        kpt_splits = [kpoints]
        label_splits = [labels]

    if cart_coords:
        coord_type = 'cartesian'
        style = Kpoints.supported_modes.Cartesian
    else:
        coord_type = 'reciprocal'
        style = Kpoints.supported_modes.Reciprocal

    kpt_files = []
    for kpt_split, label_split in zip(kpt_splits, label_splits):
        if ibzkpt:
            # hybrid calculation so set k-point weights to 0
            kpt_weights = ibzkpt.kpts_weights + [0] * len(kpt_split)
            kpt_split = ibzkpt.kpts + kpt_split
            label_split = ibzkpt.labels + label_split
        else:
            # non-SCF calculation so set k-point weights to 1
            kpt_weights = [1] * len(kpt_split)

        segment = ' -> '.join([label for label in label_split if label])
        kpt_file = Kpoints(comment=segment, num_kpts=len(kpt_split),
                           kpts=kpt_split, kpts_weights=kpt_weights,
                           style=style, coord_type=coord_type,
                           labels=label_split)
        kpt_files.append(kpt_file)

    # TODO: fix this
    # pad = math.floor(math.log(len(kpt_files))) + 2  # pad split name with zero
    if make_folders:
        for i, kpt_file in enumerate(kpt_files):
            folder = 'split-{:01d}'.format(i + 1)
            if directory:
                folder = os.path.join(directory, folder)
            os.makedirs(folder)

            kpt_file.write_file(os.path.join(folder, 'KPOINTS'))
            vasp_files = [filename, "INCAR", "POTCAR", "job"]
            vasp_files += [] if ibzkpt else ['CHGCAR']
            for vasp_file in vasp_files:
                if os.path.isfile(vasp_file):
                    shutil.copyfile(vasp_file, folder)
                else:
                    logging.warning('\nWARNING: could not find {} to copy'.
                                    format(vasp_file))
    else:
        for i, kpt_file in enumerate(kpt_files):
            kpt_filename = 'KPOINTS_split-{:0d}'.format(i + 1)
            if directory:
                kpt_filename = os.path.join(directory, kpt_filename)
            kpt_file.write_file(kpt_filename)


def parse_kpoint_list(kpt_list_str):
    return []


def main():
    parser = argparse.ArgumentParser(description="""
    kgen generates KPOINTS files for running band structure calculations in
    VASP. The high symmetry k-point paths defined in Bradley and Cracknell are
    used by default""",
                                     epilog="""
    Author: {}
    Version: {}
    Last updated: {}""".format(__author__, __version__, __date__))

    parser.add_argument('-p', '--poscar', default='POSCAR',
                        help='input VASP structure, default is POSCAR',)
    parser.add_argument('-d', '--directory', type=str, default=None,
                        help='output directory for files')
    parser.add_argument('-f', '--folders', action='store_true',
                        help="""generate calculation folders and copy in
                        necessary files""")
    parser.add_argument('-s', '--split', type=int, default=None,
                        help="number of k-points to include per split")
    parser.add_argument('-y', '--hybrid', default=False,
                        help="""append generated k-points to IBZKPT file with
                        zero weight (needed for hybrid band structures)""")
    parser.add_argument('--symprec', default=0.01, type=float,
                        help='tolerance for finding symmetry, default is 0.01')
    parser.add_argument('--spg', type=int, default=None,
                        help='space group number to override detected symmetry')
    parser.add_argument('--density', type=int, default=20,
                        help='k-point density along high symmetry lines')
    parser.add_argument('--seekpath', action='store_true',
                        help='use seekpath to generate the high-symmetry path')
    parser.add_argument('--pymatgen', action='store_true',
                        help='use pymatgen to generate the high-symmetry path')
    parser.add_argument('--cartesian', action='store_true',
                        help='use cartesian rather than fractional coordinates')

    args = parser.parse_args()
    logging.basicConfig(filename='vaspy-kgen.log', level=logging.DEBUG,
                        filemode='w', format='%(message)s')
    console = logging.StreamHandler()
    logging.info(" ".join(sys.argv[:]))
    logging.getLogger('').addHandler(console)

    mode = 'bradcrack'
    if args.seekpath:
        mode = 'seekpath'
    elif args.pymatgen:
        mode = 'pymatgen'

    ibzkpt = 'IBZKPT' if args.hybrid else None

    kgen(args.poscar, directory=args.directory, symprec=args.symprec,
         make_folders=args.folders, kpts_per_split=args.split,
         ibzkpt=ibzkpt, spg=args.spg, density=args.density, mode=mode,
         cart_coords=args.cartesian)

if __name__ == "__main__":
    main()