#!/usr/bin/env python
# vim: set fileencoding=utf-8 :
# Manuel Guenther <Manuel.Guenther@idiap.ch>

import bob
import numpy

from .Tool import Tool

class GaborJetTool (Tool):
  """Tool chain for computing Gabor jets, Gabor graphs, and Gabor graph comparisons"""

  def __init__(self, setup):
    Tool.__init__(self)
    # graph machine for enrolling models and comparing graphs
    self.m_graph_machine = bob.machine.GaborGraphMachine()
    # the Gabor wavelet transform; used by (some of) the Gabor jet similarities
    gabor_wavelet_transform = bob.ip.GaborWaveletTransform(
          number_of_angles = setup.GABOR_DIRECTIONS,
          number_of_scales = setup.GABOR_SCALES,
          sigma = setup.GABOR_SIGMA,
          k_max = setup.GABOR_MAXIMUM_FREQUENCY,
          k_fac = setup.GABOR_FREQUENCY_STEP,
          pow_of_k = setup.GABOR_POWER_OF_K,
          dc_free = setup.GABOR_DC_FREE
    )
    # jet comparison function
    self.m_similarity_function = bob.machine.GaborJetSimilarity(setup.GABOR_JET_SIMILARITY_TYPE, gabor_wavelet_transform)
    # do model averaging?
    self.m_average_model = setup.EXTRACT_AVERAGED_MODELS


  def enroll(self, enroll_features):
    """Enrolls the model by computing an average graph for each model"""
    graph_count = len(enroll_features)

    c = 0 # counts the number of enrollment files
    shape = list(enroll_features[0].shape)
    shape.insert(0, graph_count)
    model = numpy.ndarray(tuple(shape), dtype=numpy.float64)
    for graph in enroll_features:
      if graph.shape != model.shape[1:]:
        raise Exception('Size mismatched')

      model[c] = graph
      c += 1

    if self.m_average_model:
      if model.ndim() != 4:
        raise Exception('Averaging is only supported when phases are included')
      # compute average model
      average = numpy.ndarray(model.shape[1:], dtype=numpy.float64)
      self.m_graph_machine.average(model, average)
      # return the average
      return average

    else:
      # return the generated model
      return model


  def score(self, model, probe):
    """Computes the score of the probe and the model"""
    return self.m_graph_machine.similarity(model, probe, self.m_similarity_function)



