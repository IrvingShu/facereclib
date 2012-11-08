#!/usr/bin/env python
# vim: set fileencoding=utf-8 :
# Manuel Guenther <Manuel.Guenther@idiap.ch>

import faceverify, faceverify_gbu, faceverify_lfw
import argparse, os, sys
import copy # for deep copies of dictionaries
from .. import utils

# the configuration read from config file
global configuration
# the place holder key given on command line
global place_holder_key
# the extracted command line arguments
global args
# the job ids as returned by the call to the faceverify function
global job_ids
# first fake job id (useful for the --dry-run option)
global fake_job_id
fake_job_id = 0
# the number of grid jobs that are executed
global job_count
# the total number of experiments run
global task_count


def command_line_options(command_line_parameters):
  # set up command line parser
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument('-c', '--configuration-file', required = True,
      help = 'The file containing the information what parameters you want to have tested.')

  parser.add_argument('-k', '--place-holder-key', default = '#',
      help = 'The place holder key that starts the place holders which will be replaced.')

  parser.add_argument('-d', '--database', required = True,
      help = 'The database that you want to execute the experiments on.')

  parser.add_argument('-b', '--sub-directory', required = True,
      help = 'The sub-directory where the files of the current experiment should be stored. Please specify a directory name with a name describing your experiment.')

  parser.add_argument('-g', '--grid',
      help = 'The SGE grid configuration')

  parser.add_argument('-p', '--preprocessed-image-directory',
      help = '(optional) The directory where to read the already preprocessed images from (no preprocessing is performed in this case).')

  parser.add_argument('-s', '--grid-database-directory', default = '.',
      help = 'Directory where the submitted.db files should be written into (will create sub-directories on need)')

  parser.add_argument('-w', '--write-commands',
      help = '(optional) The file name where to write the calls into (will not write the dependencies, though)')

  parser.add_argument('-q', '--dry-run', action='store_true',
      help = 'Just write the commands to console and mimic dependencies, but do not execute the commands')

  parser.add_argument('-Q', '--non-existent-only', type=str,
      help = 'Only start the experiments that have not been executed successfully (i.e., where the given output directory does not exist yet)')

  parser.add_argument('parameters', nargs = argparse.REMAINDER,
      help = "Parameters directly passed to the face verify script. It should at least include the -d (and the -g) option. Use -- to separate this parameters from the parameters of this script. See 'bin/faceverify.py --help' for a complete list of options.")

  utils.add_logger_command_line_option(parser)

  global args
  args = parser.parse_args(command_line_parameters)
  utils.set_verbosity_level(args.verbose)



def extract_values(replacements, indices):
  """Extracts the value dictionary from the given dictionary of replacements"""
  extracted_values = {}
  for place_holder in replacements.keys():
    # get all occurrences of the place holder key
    parts = place_holder.split(place_holder_key)
    # only one part -> no place holder key found -> no strings to be extracted
    if len(parts) == 1:
      continue

    keys = [part[:1] for part in parts[1:]]

    value_index = indices[place_holder]

    entries = replacements[place_holder]
    entry_key = sorted(entries.keys())[value_index]

    # check that the keys are unique
    for key in keys:
      if key in extracted_values:
        raise ValueError("The replacement key '%s' was defined multiple times. Please use each key only once."%key)

    # extract values
    if len(keys) == 1:
      extracted_values[keys[0]] = entries[entry_key]

    else:
      for i in range(len(keys)):
        extracted_values[keys[i]] = entries[entry_key][i]

  return extracted_values


def replace(string, replacements):
  """Replaces the place holders in the given string with the according values from the values dictionary."""
  # get all occurrences of the place holder key
  parts = string.split(place_holder_key)
  # only one part -> no place holder key found -> return the whole string
  if len(parts) == 1:
    return string

  keys = [part[:1] for part in parts[1:]]

  retval = parts[0]
  for i in range(0, len(keys)):
    # replace the place holder by the desired string and add the remaining of the command
    retval += str(replacements[keys[i]]) + str(parts[i+1][1:])

  return '"' + retval + '"'


def create_command_line(replacements):
  """Creates the parameters for the function call that will be given to the faceverify script."""
  # get the values to be replaced with
  values = {}
  for key in configuration.replace:
    values.update(extract_values(configuration.replace[key], replacements))
  # replace the place holders with the values
  return [
      '--database', args.database,
      '--preprocessing', replace(configuration.preprocessor, values),
      '--features', replace(configuration.feature_extractor, values),
      '--tool', replace(configuration.tool, values),
      '--imports'
  ] + configuration.imports



# The different steps of the preprocessing chain.
# Use these keywords to change parameters of the specific part
steps = ['preprocessing', 'extraction', 'projection', 'enrollment', 'scoring']

# Parts that could be skipped when the dependecies are on the indexed level
skips = [[''],
         ['--skip-preprocessing'],
         ['--skip-extractor-training', '--skip-extraction'],
         ['--skip-projector-training', '--skip-projection'],
         ['--skip-enroller-training', '--skip-enrollment']
        ]

# The keywords to parse the job ids to get the according dependencies right
dependency_keys  = ['DUMMY', 'preprocess', 'extract', 'project', 'enroll']


def directory_parameters(directories):
  """This function generates the faceverify parameters that define the directories, where the data is stored.
  The directories are set such that data is reused whenever possible, but disjoint if needed."""
  def join_dirs(index, subdir):
    # collect sub-directories
    dirs = []
    for i in range(index+1):
      dirs.extend(directories[steps[i]])
    if not dirs:
      return subdir
    else:
      dir = dirs[0]
      for d in dirs[1:]:
        dir = os.path.join(dir, d)
      return os.path.join(dir, subdir)

  global args
  parameters = []
  db_file_name = 'submitted.db'

  # add directory parameters
  # - preprocessing
  if args.preprocessed_image_directory:
    parameters.extend(['--preprocessed-image-directory', os.path.join(args.preprocessed_image_directory, join_dirs(0, 'preprocessed'))] + skips[1])
  else:
    parameters.extend(['--preprocessed-image-directory', join_dirs(0, 'preprocessed')])

  # - feature extraction
  parameters.extend(['--features-directory', join_dirs(1, 'features')])
  parameters.extend(['--extractor-file', join_dirs(1, 'Extractor.hdf5')])

  # - feature projection
  parameters.extend(['--projected-features-directory', join_dirs(2, 'projected')])
  parameters.extend(['--projector-file', join_dirs(2, 'Projector.hdf5')])

  # - model enrollment
  # TODO: other parameters for other scripts?
  parameters.extend(['--models-directories', join_dirs(3, 'N-Models'), join_dirs(3, 'T-Models')])
  parameters.extend(['--enroller-file', join_dirs(3, 'Enroler.hdf5')])

  # - scoring
  parameters.extend(['--score-sub-directory', join_dirs(4, 'scores')])

  parameters.extend(['--sub-directory', args.sub_directory])

  # grid database
  dbfile = os.path.join(args.grid_database_directory, 'submitted.db')
  for i in range(len(steps)):
    if len(directories[steps[i]]):
      dbfile = os.path.join(args.grid_database_directory, join_dirs(i, 'submitted.db'))
  utils.ensure_dir(os.path.dirname(dbfile))
  parameters.extend(['--submit-db-file', dbfile])

  return parameters


def execute_dependent_task(command_line, directories, dependency_level):
  # add other command line arguments
  command_line.extend(args.parameters[1:])
  if args.grid:
    command_line.extend(['--grid', args.grid])
  if args.verbose:
    command_line.append('-' + 'v'*args.verbose)

  # create directory parameters
  command_line.extend(directory_parameters(directories))

  # add skip parameters according to the dependency level
  for i in range(1, dependency_level+1):
    command_line.extend(skips[i])

  # write the command to file?
  if args.write_commands:
    index = command_line.index('--submit-db-file')
    command_file = os.path.join(os.path.dirname(command_line[index+1]), args.write_commands)
    with open(command_file, 'w') as f:
      f.write('bin/faceverify.py ')
      for p in command_line:
        f.write(p + ' ')
      f.close()
    utils.info("Wrote command line into file '%s'" % command_file)

  # extract dependencies
  global job_ids
  dependencies = []
  for k in sorted(job_ids.keys()):
    for i in range(1, dependency_level+1):
      if k.find(dependency_keys[i]) != -1:
        dependencies.append(job_ids[k])

  # execute the command
  new_job_ids = {}
  try:
    verif_args = faceverify.parse_args(command_line)
    if args.dry_run:
      print "Would have executed job",
      print " ".join(command_line)
      print "with dependencies", dependencies
    else:
      # execute the face verification experiment
      global fake_job_id
      new_job_ids = faceverify.face_verify(verif_args, command_line, external_dependencies = dependencies, external_fake_job_id = fake_job_id)

  except Exception as e:
    utils.error("The execution of job was rejected!\n%s\n Reason:\n%s"%(" ".join(command_line), e))

  # some statistics
  global job_count, task_count
  job_count += len(new_job_ids)
  task_count += 1
  fake_job_id += 100
  job_ids.update(new_job_ids)


def create_recursive(replace_dict, step_index, directories, dependency_level, keys=[]):
  """Iterates through all the keywords and replaces all place holders with all keywords in a defined order."""

  # check if we are at the lowest level
  if step_index == len(steps):
    # create a call and execute it
    execute_dependent_task(create_command_line(replace_dict), directories, dependency_level)
  else:
    if steps[step_index] not in directories:
      directories[steps[step_index]] = []

    # we are at another level
    if steps[step_index] not in configuration.replace.keys():
      # nothing to be replaced here, so just go to the next level
      create_recursive(replace_dict, step_index+1, directories, dependency_level)
    else:
      # iterate through the keys
      if keys == []:
        # call this function recursively by defining the set of keys that we need
        create_recursive(replace_dict, step_index, directories, dependency_level, keys = configuration.replace[steps[step_index]].keys())
      else:
        # create a deep copy of the replacement dict to be able to modify it
        replace_dict_copy = copy.deepcopy(replace_dict)
        directories_copy = copy.deepcopy(directories)
        # iterate over all replacements for the first of the keys
        key = keys[0]
        replacement_directories = sorted(configuration.replace[steps[step_index]][key])
        directories_copy[steps[step_index]].append("")
        new_dependency_level = dependency_level
        for replacement_index in range(len(replacement_directories)):
          # increase the counter of the current replacement
          replace_dict_copy[key] = replacement_index
          directories_copy[steps[step_index]][-1] = replacement_directories[replacement_index]
          # call the function recursively
          if len(keys) == 1:
            # we have to go to the next level
            create_recursive(replace_dict_copy, step_index+1, directories_copy, new_dependency_level)
          else:
            # we have to subtract the keys
            create_recursive(replace_dict_copy, step_index, directories_copy, new_dependency_level, keys = keys[1:])
          new_dependency_level = step_index


def main(command_line_parameters = sys.argv[1:]):
  """Main entry point for the parameter test. Try --help to see the parameters that can be specified."""

  global task_count, job_count, job_ids
  job_count = 0
  task_count = 0
  job_ids = {}

  command_line_options(command_line_parameters)

  global configuration, place_holder_key
  configuration = utils.resources.read_config_file(args.configuration_file)
  place_holder_key = args.place_holder_key

  for attribute in ('preprocessor', 'feature_extractor', 'tool', 'replace'):
    if not hasattr(configuration, attribute):
      raise ValueError("The given configuration file '%s' does not contain the required attribute '%s'" %(args.configuration_file, attribute))

  # extract the dictionary of replacements from the configuration
  if not hasattr(configuration, 'replace'):
    raise ValueError("Please define a set of replacements using the 'replace' keyword.")
  if not hasattr(configuration, 'imports'):
    configuration.imports = ['facereclib']
    utils.info("No 'imports' specified in configuration file '%s' -> using default %s" %(args.configuration_file, configuration.imports))

  replace_dict = {}
  for step, replacements in configuration.replace.iteritems():
    for key in replacements.keys():
      if key in replace_dict:
        raise ValueError("The replacement key '%s' was defined multiple times. Please use each key only once.")
      # we always start with index 0.
      replace_dict[key] = 0

  # now, iterate through the list of replacements and create the according calls
  create_recursive(replace_dict, step_index = 0, directories = {}, dependency_level = 0)

  # finally, write some information about the
  utils.info("The number of executed tasks is: %d, which are split up into %d jobs that are executed in the grid" %(task_count, job_count))


if __name__ == "__main__":
  main()
