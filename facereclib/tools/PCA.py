#!/usr/bin/env python
# vim: set fileencoding=utf-8 :
# Manuel Guenther <Manuel.Guenther@idiap.ch>

import bob
import numpy

from .Tool import Tool
from .. import utils

class PCATool (Tool):
  """Tool for computing eigenfaces"""

  def __init__(
      self,
      subspace_dimension,
      distance_function = bob.math.euclidean_distance,
      is_distance_function = True,
      uses_variances = False
  ):

    """Initializes the PCA tool with the given setup"""
    # call base class constructor and register that the tool performs a projection
    Tool.__init__(self, performs_projection = True)

    self.m_subspace_dim = subspace_dimension
    self.m_machine = None
    self.m_distance_function = distance_function
    self.m_factor = -1 if is_distance_function else 1.
    self.m_uses_variances = uses_variances


  def train_projector(self, training_features, projector_file):
    """Generates the PCA covariance matrix"""
    # Initializes the data
    data = numpy.vstack([feature.flatten() for feature in training_features])

    utils.info("  -> Training LinearMachine using PCA (SVD)")
    t = bob.trainer.SVDPCATrainer()
    self.m_machine, self.m_variances = t.train(data)
    # Machine: get shape, then resize
    self.m_machine.resize(self.m_machine.shape[0], self.m_subspace_dim)
    self.m_variances.resize(self.m_subspace_dim)

    f = bob.io.HDF5File(projector_file, "w")
    f.set("Eigenvalues", self.m_variances)
    f.create_group("Machine")
    f.cd("/Machine")
    self.m_machine.save(f)


  def load_projector(self, projector_file):
    """Reads the PCA projection matrix from file"""
    # read PCA projector
    f = bob.io.HDF5File(projector_file)
    self.m_vairances = f.read("Eigenvalues")
    f.cd("/Machine")
    self.m_machine = bob.machine.LinearMachine(f)
    # Allocates an array for the projected data
    self.m_projected_feature = numpy.ndarray(self.m_machine.shape[1], numpy.float64)

  def project(self, feature):
    """Projects the data using the stored covariance matrix"""
    # Projects the data
    self.m_machine(feature, self.m_projected_feature)
    # return the projected data
    return self.m_projected_feature

  def enroll(self, enroll_features):
    """Enrolls the model by computing an average of the given input vectors"""
    model = None
    for feature in enroll_features:
      if model == None:
        model = numpy.zeros(feature.shape, numpy.float64)

      model[:] += feature[:]

    # Normalizes the model
    model /= float(len(enroll_features))

    # return enrolled model
    return model


  def score(self, model, probe):
    """Computes the distance of the model to the probe using the distance function taken from the config file"""
    # return the negative distance (as a similarity measure)
    if self.m_uses_variances:
      return self.m_factor * self.m_distance_function(model, probe, self.m_variances)
    else:
      return self.m_factor * self.m_distance_function(model, probe)

