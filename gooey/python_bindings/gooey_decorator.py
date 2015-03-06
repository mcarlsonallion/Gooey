"""
Created on Jan 24, 2014

@author: Chris

Hey, whaduya know. This is out of date again. TODO: update giant doctring.


##How things work these days (though, likely to change)

The decorator is used solely as a nice way to get the location
of the executing script. It no longer returns a decorated version
of the client code, but in fact completely hijacks the execution.
So, rather than returning a reference to the client's main, it now
returns itself, thus short-circuiting the execution of the client
program.

What it DOES do now is grab where the client module is stored and
read it in as a file so that it can hack away at it.

The first step, as before, is getting the ArgumentParser reference
so that the needed values can be extracted. This is done by reading
the source file up to the point where the `parse_args()` method is
called. This puts us smack in the middle of the client's `main` method.

This first half guarantees that all imports, modules, variable assignments,
etc.. are caught (unlike before).

Next step: getting the rest of the source code that's relevant

The file is again read up to the `parse_args` call, but this time everything
leading up to that point is dropped and we keep only the remainder of the file.
So, now the top and the bottom is located, but the bottom needs to be trimmed a
little more -- we want to drop everything remaining in the main method.

So, we `dropwhile` lines are currently indented (and thus still part of the `main`
method)

Finally, we arrive at the end, which gives us an exact copy of the original source
file, minus all of it's main logic. The two pieces are then sandwiched together,
saved to a file, and imported as a new module. Now all that has to be done is call
it (moddified) main function, and bam! It returns to fully populated parser object
to us. No more complicated ast stuff. Just a little bit of string parsing and we're
done."""

import os
import tempfile
import wx
import source_parser
import atexit
from functools import partial
from gooey.gui.lang import i18n
from gooey.gui.windows import layouts
from gooey.python_bindings import argparse_to_json


def Gooey(f=None, advanced=True, language='english', show_config=True, 
      program_name=None, program_description=None):
  """Decorator for client code's main function.
  Entry point for the GUI generator.

  Scans the client code for argparse data. If found, extracts it and build 
  the proper configuration gui windows (basic or advanced).

  :param f: The function being decorated. Note it's not actually called, just used as a reference.
  :type f: callable
  :param advanced: Whether to show advanced config or not 
  :type advanced: bool
  :param language: Translations configurable via json
  :type language: str
  :param show_config: Skip config screens all together
  :type show_config: bool
  :param program_name: Defaults to script name 
  :type program_name: str or None
  :param program_description: Defaults to ArgParse Description
  :type program_description: str or None
  :rtpye: callable"""

  params = locals()

  def build(payload):
    """Returns a function called inner() and sets its __name__ to payload's.

    :param payload: The (decorated) main function from the module
    :type payload: callable
    :rtype: callable"""
    def inner():
      #because nonlocal keyword doesn't exist yet :(
      show_config = params['show_config'] 

      main_module_path = get_caller_path()
      filename = os.path.basename(main_module_path)
      cleaned_source = clean_source(main_module_path)

      ### Create a temp file
      descriptor, tmp_filepath = tempfile.mkstemp(suffix='.py')
      atexit.register(cleanup, descriptor, tmp_filepath)

      ### write the source to the tmp file without the decorator @gooey
      with open(tmp_filepath, 'w') as f:
        f.write(cleaned_source)

      ### If there aren't any args that get parsed, skip the config phase
      if not has_argparse(cleaned_source):
        show_config = False

      ### Run command for our new version
      run_cmd = 'python {}'.format(tmp_filepath)

      # Must be called before anything else
      app = wx.App(False)

      i18n.load(language)

      # load gui components after loading the language pack
      from gooey.gui.client_app import ClientApp
      from gooey.gui.client_app import EmptyClientApp
      from gooey.gui.windows.base_window import BaseWindow
      from gooey.gui.windows.advanced_config import AdvancedConfigPanel
      from gooey.gui.windows.basic_config_panel import BasicConfigPanel

      meta = {
        'target': run_cmd,
        'program_name': program_name,
        'program_description': program_description or '',
        'show_config': show_config,
        'show_advanced': advanced,
        'default_size': (610, 530),
        'requireds_cols': 1,
        'optionals_cols': 2,
        'manual_start': False
      }

      if show_config:
        parser = get_parser(main_module_path)
        meta['program_description'] = parser.description or program_description

        client_app = ClientApp(parser, payload)

        if advanced:
          build_spec = dict(meta.items() +\
                    argparse_to_json.convert(parser).items())
          BodyPanel = partial(AdvancedConfigPanel, 
                    build_spec=build_spec)
        else:
          build_spec = dict(meta.items() +\
                    layouts.basic_config.items())
          BodyPanel = partial(AdvancedConfigPanel, 
                    build_spec=build_spec)
      # User doesn't want to display configuration screen
      # Just jump straight to the run panel
      else:
        build_spec = dict(meta.items() + layouts.basic_config.items())
        build_spec['manual_start'] = True
        BodyPanel = partial(AdvancedConfigPanel, build_spec=build_spec)
        client_app = EmptyClientApp(payload)


      frame = BaseWindow(BodyPanel, build_spec, params)

      if not show_config:
        frame.ManualStart()
      frame.Show(True)
      app.MainLoop()

    inner.__name__ = payload.__name__
    return inner

  ### If f is callable return build of f, otherwise return build.
  if callable(f):
    return build(f)
  return build

def clean_source(module_path):
  """Returns the text of the module stripping out the decorator @gooey

  :param module_path: sys.argv[0], the path to the module including the file name.
  :type module_path: str
  :rtype: str"""
  with open(module_path, 'r') as f:
    return ''.join(
      line for line in f.readlines()
      if '@gooey' not in line.lower())


def get_parser(module_path):
  """Wrapper for source_parser.extract_parser. 

  :param module_path: sys.argv[0], the path to the module including the file name.
  :type module_path: str
  :rtype: callable"""
  return source_parser.extract_parser(module_path)

def get_caller_path():
  """Gets the path to the module from sys.argv.

  :rtype: str"""
  tmp_sys = __import__('sys')
  return tmp_sys.argv[0]

def has_argparse(source):
  """Confirms that the module calls .parse_args somewhere in its source.

  :param source: source code of the module.
  :type source: str
  :rtype: bool"""
  bla = ['.parse_args()' in line.lower() for line in source.split('\n')]
  return any(bla)

def cleanup(descriptor, filepath):
  """This function runs upon normal program termination. It closes the 
  descriptor to the temp file and deletes it.

  :param descriptor: File descriptor of the temp file
  :type descriptor: int
  :param filepath: Path to the temp file
  :type filepath: str
  :rtype: None"""
  os.close(descriptor)
  os.remove(filepath)


if __name__ == '__main__':
  pass
