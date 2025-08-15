
import subprocess
from .errors import plugin_fail

class Commander():
  """Commander
  
  A class to represent a shell executable. The only constructor arg
  is the name of the entrypoint. Now a cli tool can pretend to be a
  class with the second arg pretending to be a method with all the
  rest of the args passed into the method. 

  Args:
    entrypoint: The path to an executable or the name of one on the path. 

  Example:
    Using the `kubectl` cli to get the default namespace: 

      from kubed.krm.cli import Commander

      k = Commander("kubectl")
      print(k.get("ns", "default"))
      
  """
  def __init__(self, entrypoint: str) -> None:
    self.__entrypoint = entrypoint
  def __getattr__(self, __name: str):
    return lambda *args : self.eval(__name, *args)
  def eval(self, *args):
    process = subprocess.Popen(
                    [self.__entrypoint, *args],
                     stdout=subprocess.PIPE, 
                     stderr=subprocess.PIPE, text=True)
    process.wait()
    stdout, stderr = process.communicate()
    if stderr:
      plugin_fail(stderr)
    return stdout