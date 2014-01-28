#!/usr/bin/env python
"""
pyOpt_gradient - A class that produce gradients using finite
difference or complex step. 

Copyright (c) 2013-2014 by Dr. Gaetan Kenway
All rights reserved.

Developers
----------
- Dr. Gaetan Kenway (GKK)

History
-------
    v. 0.1  - Initial Class Creation (GKK)
"""
# =============================================================================
# External Python modules
# =============================================================================
import numpy

# =============================================================================
# Gradient Class
# =============================================================================
class Gradient(object):
    """
    Gradient class for automatically computing gradients with finite
    difference or complex step. 

    Parameters
    ----------
    optProb : Optimization instance
        This is the complete description of the optimization problem. 

    sensType : str
        'FD' for finite difference, 'CS' for complex step

    sensStep : number
        Step size to use for differencing

    sensMode : str
        Flag to compute gradients in parallel.

    comm : MPI Intra communicator
        Specifiy a MPI comm to use. Default is None. If mpi4py is not
        available, the serial mode will still work. if mpi4py *is*
        available, comm defaluts to MPI.COMM_WORLD. 
        """
    
    def __init__(self, optProb, sensType, sensStep=None, sensMode='', comm=None):
        
        self.optProb = optProb
        self.sensType = sensType
        if sensStep is None:
            if self.sensType == 'fd':
                self.sensStep = 1e-6
            else:
                self.sensStep = 1e-40j
        self.sensMode = sensMode
        if comm is None:
            # Two things can happen: we don't *actually* have MPI,
            # which means the calcuation *must* be serial, or we can
            # import MPI in which case, the comm will default to
            # MPI.COMM_WORLD
            try:
                from mpi4py import MPI
                self.comm = MPI.COMM_WORLD
                self.MPI = MPI
            except ImportError:
                self.comm = None
            # end try
        else:
            self.comm = comm
        # end if

        # Now we can compute which dvs each process will need to
        # compute:
        ndvs = self.optProb.ndvs
        if self.sensMode == 'pgc' and self.comm:
            self.mydvs = list(range(self.comm.rank, ndvs, self.comm.size))
        else:
            self.mydvs = list(range(ndvs))
        return

    def __call__(self, x, fobj, fcon):
        """
        We need to make this object "look" the same as a user supplied
        function handle. That way, the optimizers need not care how
        the gradients are **actually** calculated. 

        Parameters
        ----------
        x : array
            Optimization variables from optimizer

        fobj : float
            Function value for the point about which we are computing
            the gradient

        fcon : array or dict
            Constraint values for the point about which we are computing
            the gradient

        Returns
        -------
        gobj : 1D array
            The derivative of the objective with respect to the design
            variables

        gcon : 2D array
            The derivative of the constraints with respect to the design
            variables

        fail : bool
            Flag for failure. It currently always returns False
            """

        # Since this is *very* dumb loop over all the design
        # variables, it is easier to just loop over the x values as an
        # array. Furthermore, since the user **should** have
        # reasonably well scaled variables, the fixed step size should
        # have more meaning. 

        # Generate final array sizes for the objective and constraint
        # gradients
        ndvs = self.optProb.ndvs
        ncon = self.optProb.nCon
        gobj = numpy.zeros(ndvs, 'd')
        gcon = numpy.zeros((ncon, ndvs), 'd')

        if self.sensMode == 'pgc':
            fobj_base = self.comm.bcast(fobj)
            fcon_base = self.comm.bcast(fcon)
        else:
            fobj_base = fobj
            fcon_base = fcon

        # We DO NOT want the constraints scaled here....the constraint
        # scaling will be taken into account when the derivatives are
        # processed as per normal.
        fcon_base = self.optProb.processConstraints(fcon_base, scaled=False)
        x_base = self.optProb.deProcessX(x)

        # Convert to complex if necessary:
        if self.sensType == 'cs':
            x_base = x_base.astype('D')

        for i in self.mydvs:
            xph = x_base.copy()
            xph[i] += self.sensStep
            
            x_call = self.optProb.processX(xph)
            # Call objective    
            [fobj_ph, fcon_ph, fail] = self.optProb.objFun(x_call)

            # Process constraint in case they are in dict form
            fcon_ph = self.optProb.processConstraints(fcon_ph, scaled=False)

            if self.sensType == 'fd':
                gobj[i]    = (fobj_ph - fobj_base)/self.sensStep
                gcon[:, i] = (fcon_ph - fcon_base)/self.sensStep
            else:
                gobj[i]    = numpy.imag(fobj_ph)/numpy.imag(self.sensStep)
                gcon[:, i] = numpy.imag(fcon_ph)/numpy.imag(self.sensStep)
            # end if
        # end for

        if self.sensMode == 'pgc':
            # We just mpi_reduce to the root with sum. This uses the
            # efficent numpy versions
            self.comm.Reduce(gobj.copy(), gobj, op=self.MPI.SUM, root=0)
            self.comm.Reduce(gcon.copy(), gcon, op=self.MPI.SUM, root=0)

        return gobj, gcon, False
        
