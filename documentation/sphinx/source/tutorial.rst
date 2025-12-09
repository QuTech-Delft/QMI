========
Tutorial
========

This tutorial presumes that you have installed QMI as described in the :doc:`installation` section.
To check if this is the case, start your favorite Python 3 interpreter and type ``import qmi``.
If this works, you're ready to go.

Hello QMI!
----------

To start using QMI, the first steps are to import the :mod:`qmi` package, and next, call :py:func:`qmi.start() <qmi.core.context_singleton.start>` with a string argument that specifies our local *QMI context name*.
The QMI context name allows other QMI programs to contact us, and to communicate with locally held instances of things like instruments and tasks that our context manages.
More on that later.

>>> import qmi
>>> qmi.start("hello_world", config_file=None)

The second argument to ``qmi.start()`` is the path to the QMI configuration file.
The first examples in this tutorial do not require a configuration file, so we specify ``None`` to indicate that no
configuration file should be used. The second argument is optional, so it can also be left out in the first examples.

The :py:func:`qmi.start() <qmi.core.context_singleton.start>` call creates a QMI Context instance that manages all
QMI-related resources. A Python process that uses QMI functionality has a single, global QMI Context.
If needed, it can be obtained directly via the :py:func:`qmi.context() <qmi.core.context_singleton.context>` call:

>>> qmi.context()
QMI_context(name='hello_world')

When a QMI context is is created, it will (optionally) read a configuration file.
It will then start a network thread in the background that allows interaction with the context from the outside world, if needed.

To end our time as a QMI-aware process, we should call :py:func:`qmi.stop() <qmi.core.context_singleton.stop>` prior to leaving Python:

>>> qmi.stop()

This allows the QMI context to stop the network connections and threads that it manages in a controlled way.

If we don't call ``qmi.stop()`` explicitly and quit Python (or a script crashes), the orderly shutdown will still be performed
as much as possible, while generating a warning message. However, an explicit close is preferable, so get it is a good habit to
include it as a final statement in your QMI scripts.

You can now exit your interactive Python session.

Controlling a QMI instrument
----------------------------

We will now show how you can use QMI to control an instrument.
For this, start a fresh Python interpreter session and start QMI:

>>> import qmi
>>> qmi.start("nsg_demo", None)

The next thing we will do is to make a so-called *QMI instrument*.
To keep this tutorial independent from the equipment you have in your lab, we will use a 'fake' measurement instrument that is included in QMI for testing purposes: a software-simulated noisy sine generator.

To make an instance of this instrument, execute the following code:

>>> from qmi.instruments.dummy.noisy_sine_generator import NoisySineGenerator
>>> nsg = qmi.make_instrument("nsg", NoisySineGenerator)

The :py:func:`qmi.make_instrument() <qmi.core.context_singleton.make_instrument>` call instructs the default context to instantiate an instrument with name *nsg* and of type :py:class:`NoisySineGenerator <qmi.instruments.dummy.noisy_sine_generator.NoisySineGenerator>`.

It is a useful convention to assign the result of the ``make_instrument()`` function to a variable with the same name as the instrument itself, as we do here.

The instrument instance itself is owned and managed by the default context; we receive a *proxy* to the NoisySineGenerator instrument, rather than a reference to the instrument itself:

>>> nsg
<rpc proxy for nsg_demo.nsg (qmi.instruments.dummy.noisy_sine_generator.NoisySineGenerator)>

In QMI, it is rare to deal with instruments directly. We mostly deal with them through proxy objects that act as a references to an actual instrument
owned by some QMI context. The advantage of this is that it is possible to have a proxy to an instrument that lives in a different QMI process,
perhaps even running on a different computer in the network - and we can use such a remote instrument as if it were local, which is pretty useful.
Thus, by using proxies to talk to instruments, QMI achieves *network transparency*.

We can look at the documentation of the Proxy instance:

>>> help(nsg)

This prints the docstring of the NoisySineGenerator class. It does also give a listing of all RPC methods, signals and class constants of the proxy instance as well.

As we can read in the help, our noisy sine generator ``nsg`` supports a bunch of methods, including the ``get_sample()`` method.
We can retrieve that method's docstring as well by typing

>>> help(nsg.get_sample)

Now, let's give it a shot and see what happens:

>>> nsg.get_sample()

Whoops, we got an error! This is because we didn't "open" the instrument first. This is of course not necessary with a virtual instrument, but we have made it to simulate a real instrument, requiring thus "open" and "close" calls for connection.

>>> nsg.open()
>>> nsg.get_sample()

Now we get returned a single value of the simulated NoiseSineGenerator device.

We can make a very basic graph of *nsg* samples as follows:

>>> import time
>>> for i in range(1000):
...     print(" " * int(40.0 + 0.25 * nsg.get_sample()) + "*")
...     time.sleep(0.01)

Feel free to experiment a bit with the other NoisySineGenerator methods, which you can read about by executing the ``help(nsg)``.

Also, if you want, have a look at the source code of ``qmi.instruments.dummy.noisy_sine_generator``.
This should convince you that implementing device drivers for QMI instruments is pretty straightforward.

When done, close the instrument and exit your Python interpreter:

>>> nsg.close()
>>> qmi.stop()

From now on, we will no longer tell you to execute ``qmi.stop()``, but don't forget to do it.

Locking an instrument
---------------------

Because QMI allows networked access to remote instruments, there is the distinct possibility that more than one user accesses the same instrument.
This can be intentional, for example a measurement script setting the frequency of a function generator while a GUI monitors and displays that frequency.
However, it can also be unintentional, for example when a scheduled calibration routine tries to calibrate an instrument that is being used for a measurement.

To prevent unintentional simultaneous access, you can lock an instrument, preventing others from using it.
Locks are owned by the proxy, and only one proxy can own a lock at any time.

Let's see how that works.
First we create a context and the instrument:

>>> qmi.start("lock_demo")
>>> qmi.make_instrument("nsg", NoisySineGenerator)
<rpc proxy for lock_demo.nsg (qmi.instruments.dummy.noisy_sine_generator.NoisySineGenerator)>

Create two proxies to the instrument:

>>> nsg1 = qmi.get_instrument("lock_demo.nsg")
>>> nsg2 = qmi.get_instrument("lock_demo.nsg")
>>> nsg1.open()
>>> nsg2.open()

Recall that there is only one NSG instrument and only one instance of the ``NoisySineGenerator`` class.
Let's lock the instrument:

>>> nsg1.lock()
True

The return value tells us that the lock was granted, as can be verified:

>>> nsg1.is_locked()
True

Note that the second proxy will also see the instrument is locked:

>>> nsg2.is_locked()
True

The first proxy can interact with the instrument, but the second one cannot, because it does not own the lock:

>>> nsg1.get_sample()
18.026037686619105
>>> nsg2.get_sample()
2021-11-30 14:50:55.786 | ERROR    | qmi.core.rpc           | nsg locked, method request without lock token is denied
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
  File "/Users/qutech/Development/qmi/qmi/qmi/core/rpc.py", line 566, in <lambda>
    blocking_rpc_method_call(self._context, self._rpc_object_address, method_name, self._lock_token,
  File "/Users/qutech/Development/qmi/qmi/qmi/core/rpc.py", line 505, in blocking_rpc_method_call
    return future.wait(rpc_timeout)
  File "/Users/qutech/Development/qmi/qmi/qmi/core/rpc.py", line 458, in wait
    raise QMI_RuntimeException("The object is locked by another proxy")
qmi.core.exceptions.QMI_RuntimeException: The object is locked by another proxy

The first proxy first needs to unlock the instrument!

>>> nsg1.unlock()
True
>>> nsg1.get_sample()
98.47301719199825
>>> nsg2.get_sample()
72.86104574567875

To unlock from another proxy, within the same context, you can specify a custom lock token.

>>> nsg1.lock(lock_token="youcanunlocktoo")
True
>>> nsg2.unlock()
2021-11-30 14:53:16.091 | WARNING  | qmi.core.rpc           | Unlocking request (token=None) for nsg failed! Locked with token=QMI_LockTokenDescriptor(context_id='lock_demo', token='$lock_2').
False
>>> nsg2.unlock(lock_token="youcanunlocktoo")
True

However, if you find yourself in a situation in which the locking proxy was lost (e.g. you closed your interactive session without unlocking), or the token is unknown, there is a force unlock method.

>>> nsg2.force_unlock()
2021-11-30 14:54:47.437 | WARNING  | qmi.core.rpc           | nsg forcefully unlocked!.
>>> nsg2.is_locked()
False

It is also possible to unlock from another instrument proxy by providing the context name as well. See the example below, how to get from another context the instrument proxy. In a new terminal window, start up Python and do the following:

>>> import qmi
>>> qmi.start("client")
>>> qmi.context().connect_to_peer("lock_demo")
>>> nsg3 = qmi.get_instrument("lock_demo.nsg")
>>> nsg3.unlock(context_name="lock_demo", lock_token="youcanunlocktoo")
True

Configuration
-------------

Many aspects of QMI are configurable via a *configuration file*.
The syntax of this file is very similar to `JSON <https://www.json.org/>`_,
but unlike JSON, the configuration file may contain comments starting with a ``#`` character.

By default, QMI attempts to read the configuration from a file named ``qmi.conf`` in
the home directory (or the user folder on Windows).
If you want to use a different file name or location, you can specify
the configuration file path either as the second argument of ``qmi.start()``
or in the environment variable ``QMI_CONFIG``.

Let's create a configuration file with the following contents::

  {
      # Log level for messages to the console.
      "logging": {
          "console_loglevel": "INFO"
      }
  }

This configuration file changes the log level for messages that appear on the screen.
By default, QMI prints only warnings and error messages.
Our new configuration also enables printing of informational messages.
For further details about logging options, see documentation on ``qmi.core.logging_init`` module.

Test the new configuration file in a new Python session:

>>> import qmi
>>> qmi.start("hello_world")

Notice that we do not pass a ``None`` as the second argument to ``qmi.start()``.
As a result, QMI will try to read the configuration file from its default location.
If your configuration file is not in the default location, you may have to specify its location
as the second argument to ``qmi.start()``.

If the configuration file is working correctly, QMI should print a bunch of log messages
after the call to ``qmi.start()``.

We will add more settings to the configuration file as we progress through this tutorial.

Accessing a remote instrument
-----------------------------

QMI makes it easy to access an instrument instance that exists in
another Python program. The programs may even run on different computers.

The Python program that contains the instrument instance must be accessible
via the network. This can be achieved by extending the QMI configuration file.
The new file will look as follows::

  {
      # Log level for messages to the console.
      "logging": {
          "console_loglevel": "INFO"
      },

      "contexts": {
          # Testing remote instrument access.
          "instr_server": {
              "host": "127.0.0.1",
              "tcp_server_port": 40001
          }
      }
  }

Note that JSON is very picky about the use of commas.
There **must** be a comma between multiple elements in the same group,
but there **may not** be a comma after the last element of a group.

Start the instrument server in a new Python session:

>>> import qmi
>>> from qmi.instruments.dummy.noisy_sine_generator import NoisySineGenerator
>>> qmi.start("instr_server")
>>> nsg = qmi.make_instrument("nsg", NoisySineGenerator)

Because the name of the context ``instr_server`` matches the name specified in the configuration file, QMI opens a TCP server port for this context.
Other Python programs can connect to this port to access the sine generator.

To try this, leave the instrument server session running and start
another Python session in a separate terminal window:

>>> import qmi
>>> qmi.start("hello_world")
>>> qmi.context().connect_to_peer("instr_server")
>>> nsg = qmi.get_instrument("instr_server.nsg")
>>> nsg.open()
>>> nsg.get_sample()

On Windows, the peer connection probably fails and you'll have to use

>>> qmi.context().connect_to_peer("instr_server", peer_address="127.0.0.1:40001")

This example demonstrates how the second Python program is able to access
the NoisySineGenerator instance that exists within the first Python program.
To do this, the QMI context of the second program connects to the
``instr_server`` context via TCP.
Behind the scenes, the two contexts exchange messages through this connection
to arrange for the method ``get_sample()`` to be called in the first program,
and the answer to be sent to the second program.

.. note::
    **issues in connecting a "remote" context**

    Sometimes the connecting to a peer context fails. One reason is that in the ``qmi.conf`` file the IP address
    or the port number is defined wrong. One way to check the available contexts to connect to is to use command
    ``qmi.show_network_contexts()`` to list available contexts, showing their name, IP-address:port anc connection
    status:

    >>> name         address         connected
    >>> ---------    --------------- ---------
    >>> instr_server 145.90.38.138:0 no
    >>> ---------    --------------- ---------

    If this doesn't match the IP:port configuration of your ``qmi.conf`` file, and you used "localhost" or "127.0.0.1" in your configuration,
    the reason is that the localhost address gets interpreted in the background as the IP address of the PC itself. But if you set something else and the
    IP addresses do no match, the connection probably fails.
    Also if the shown IP:port is not the one you defined in ``qmi.conf`` of ``instr_server``, the IP:Port you gave is not in the valid range of your system. In this case, ``qmi`` just sets other values in correct range.
    If only the port number does not match, it might be possible the the ``qmi.conf`` was actually not read and QMI has set default (localhost) values. In that case,
    define the config file location manually in ``qmi.start`` call.

    >>> qmi.start("instr_server", config_file="<path_to_qmi.conf>")

    **Linux**

    In case you did not specify the IP:port in the ``qmi.conf`` file, you then need to specify it like this:

    >>> qmi.context().connect_to_peer("instr_server", "145.90.38.138:0")

    The IP address can be also "localhost" or "127.0.0.1" if that is used in the ``qmi.conf``.

    **Windows**

    If the port number is `0`, and you are on a Windows machine, trying to connect this peer will give you an error:

    >>> OSError: [WinError 10049] The requested address is not valid in its context

    While on Linux this usually works, Windows does not allow this and you have to specify a non-zero port number for the context.
    On most systems, port numbers up to 1023 are mostly reserved so it is best to use a port number > 1023.


Using the 'autoconnect' option
------------------------------

You can also use the `autoconnect` option in ``get_instrument`` to skip the step ``connect_to_peer``:

>>> import qmi
>>> qmi.start("hello_world")
>>> nsg = qmi.get_instrument("instr_server.nsg", auto_connect=True, host_port="145.90.38.138:54704")
>>> nsg.open()
>>> nsg.get_sample()
>>> -86.43253254643

One handy way of avoiding possible mistakes in defining the IP:port in ``qmi.conf`` is to use following short script:

>>> contexts = qmi.context().discover_peer_contexts()
>>> for ctx in contexts:
>>>    if ctx[0] == "instr_server":
>>>         nsg = qmi.get_instrument("instr_server.nsg", auto_connect=True, host_port=ctx[1])
>>>         break
>>>
>>> nsg.get_sample()  # will raise an exception if "instr_server" was not found in ``contexts``
>>> 60.1239025839


A simple QMI measurement script
-------------------------------

Up to this point, this tutorial has demonstrated QMI in interactive Python sessions.
For more complicated work, it is often convenient to create a dedicated Python script.

To set up a simple measurement script, create a file ``measure_demo.py`` with the following content::

    #!/usr/bin/env python

    import qmi
    from qmi.utils.context_managers import start_stop
    from qmi.instruments.dummy.noisy_sine_generator import NoisySineGenerator

    def measure_data(nsg):
        samples = []
        for i in range(1000):
            s = nsg.get_sample()
            samples.append(s)
        print("number of samples:", len(samples))
        print("mean sample value:", sum(samples) / len(samples))

    def main():
        with start_stop(qmi, "measure_demo"):
            with qmi.make_instrument("nsg", NoisySineGenerator) as nsg:
                measure_data(nsg)

    if __name__ == "__main__":
        main()

Run the new script by typing the following command in a shell terminal::

    python measure_demo.py

Note that the script uses :py:class:`qmi.utils.context_managers.start_stop` to start and stop the QMI framework.
This is just a convenient way to make sure that ``qmi.start()`` and ``qmi.stop()`` will always be called.
Similarly, the `QMI_Instrument` objects are equipped with context managers that open and close the the instrument, calling ``nsg.open()`` and ``nsg.close()`` at the creation and destruction of the instance.

.. note::
    Some users prefer to invoke scripts from an interactive Python session,
    using tricks based on ``execfile`` or ``reload`` commands.
    We do not recommend this.
    Running multiple scripts (or versions) in the same Python session
    causes the scripts to affect each other in ways that are difficult to predict,
    and produces errors that are hard to track down.
    To avoid this, simply run each script in a separate Python process from the shell command line.

Making a QMI task
-----------------

In some cases, it may be necessary to perform measurements while
simultaneously running a continuous background task.
A good example could be a control loop, which measures a signal and
a corresponding adjustment of a parameter at a regular interval.

A *QMI Task* is a procedure which runs independently and continuously
in the background inside a Python program.
The same program can perform different activities in its main control
flow while the task continues run in a separate background thread.

Creating a custom task involves creating a Python class which derives
from :py:class:`qmi.core.task.QMI_Task`.
To ensure that the task works correctly and remains accessible by
remote Python programs, it should be defined in a *Python module*
instead of the top-level script file.

To demonstrate a custom task, create a new Python module inside
the module path for your project. If you don't have a module path
yet, just create a file ``demo_task.py`` in the current directory::

    import qmi
    from qmi.core.task import QMI_Task

    class DemoTask(QMI_Task):

        def run(self):
            print("starting the background task")
            nsg = qmi.get_instrument("task_demo.nsg")
            while True:
                sample = nsg.get_sample()
                amplitude = nsg.get_amplitude()
                if abs(sample) > 10:
                    amplitude *= 0.9
                else:
                    amplitude *= 1.1
                nsg.set_amplitude(amplitude)
                self.sleep(0.1)

Note that we define a custom class ``DemoTask`` with one special method named ``run()``.
This method contains the code that makes up the background task.
In this simple example, the task simply loops 10 times per second, reading a sample
from the sine generator and adjusting its amplitude.
The task uses the function :py:func:`qmi.core.task.QMI_Task.sleep` to sleep instead
of ``time.sleep()``. The advantage of ``QMI_Task.sleep()`` is that it stops waiting
immediately when it is necessary to stop the task.

Finally, create a top-level script ``task_demo.py`` which starts
the task and continues to perform other activities::

    #!/usr/bin/env python

    import time
    import qmi
    from qmi.utils.context_managers import start_stop
    from qmi.instruments.dummy.noisy_sine_generator import NoisySineGenerator
    from demo_task import DemoTask

    def main():
        with start_stop(qmi, "task_demo"):
            with qmi.make_instrument("nsg", NoisySineGenerator) as nsg:
                task = qmi.make_task("task", DemoTask)
                task.start()
                print("the task has been started")
                time.sleep(1)
                for i in range(5):
                    print("amplitude =", nsg.get_amplitude())
                    time.sleep(1)
                task.stop()
                task.join()
                print("the task has been stopped")

    if __name__ == "__main__":
        main()

Note that the main script creates an instance of the ``NoisySineGenerator``
just like in previous demos.
This instance of the sine generator will also be used by the background task.
Next, the script uses :py:func:`qmi.make_task() <qmi.core.context_singleton.make_task>`
to create an instance of ``DemoTask``.
After creating the task, it needs to be started by calling the method
:py:func:`task.start() <qmi.core.task.QMI_TaskRunner.start>`.
From that point on, the task runs in the background while the main script
keeps its hands free to do other things.
In this example, it just reads the amplitude of the sine generator
a couple of times.
Eventually, the main script calls the methods :py:func:`task.stop() <qmi.core.task.QMI_TaskRunner.stop>`
to tell the task to stop, followed by :py:func:`task.join() <qmi.core.task.QMI_TaskRunner.join>`
to wait until the task is fully stopped.

Run the script from the shell command line::

    python task_demo.py

The script prints a warning when the task stops.
This happens because stopping the task raises
:py:class:`QMI_TaskStopException <qmi.core.exceptions.QMI_TaskStopException>`
in response to the call ``task.stop()``.
The warning looks rather impressive since it also dumps a stack trace,
but it is quite harmless.

Using the QMI_LoopTask to make a task
-------------------------------------

In the above example we could instead of "regular" task, create a **QMI_LoopTask** instance::

    from qmi.core.task import QMI_LoopTask
    ...

    class DemoLoopTask(QMI_LoopTask):
        def loop_prepare(self):
            # get the instrument
            self.nsg = qmi.get_instrument("task_demo.nsg")

        def loop_iteration(self):
            # Define the period actions
            sample = self.nsg.get_sample()
            amplitude = self.nsg.get_amplitude()
            if abs(sample) > 10:
                amplitude *= 0.9
            else:
                amplitude *= 1.1
            self.nsg.set_amplitude(amplitude)

The **QMI_LoopTask subclass** ``__init__()`` takes additional parameters `loop_period` and `policy`. These additional parameters
can be passed to `context.make_task()`. In the ``task_demo.py`` edit the ``make_task`` call to be::

    from qmi.core.task import QMI_LoopTaskMissedLoopPolicy
    from demo_task import DemoLoopTask
    ...
                task = qmi.make_task("task", DemoLoopTask, loop_period=1E-6, policy=QMI_LoopTaskMissedLoopPolicy.SKIP)
                task.start()
                print("the task has been started")
                time.sleep(1E-5)
                for i in range(5):
                    print("amplitude =", nsg.get_amplitude())
                    time.sleep(1E-5)
                task.stop()
                task.join()
                print("the task has been stopped")

Now, the task runs at loop period of 1 us, and if executing the ``loop_iteration`` function takes longer than the ``loop_period``,
it just skips to the next scheduled period, instead of trying to do the following period a.s.a.p. (``IMMEDIATE`` policy, which is default).
This is probably useful in cases where we can get data at specific moments of time ONLY, but due to the high frequency of the loop period we cannot
always do this. The third option is ``TERMINATE`` which stops the loop if a period gets overdue.

Tasks and RPC methods
---------------------

Tasks cannot have RPC methods in them by design choice. But, nevertheless in some special cases the user might like to monitor and control
a value or values at some unknown moment while the task is running. For example, we would like to retrieve and control the ``amplitude`` value
of our ``DemoTask``. To do this, first we need to make an attribute for the object by introducing it in ``__init__``::

   def __init__(self, task_runner, name, amplitude_factor=1.0):
        super().__init__(task_runner, name)
        self.amplitude_factor = amplitude_factor
        ...
        # and we can modify in the while-loop 'amplitude' with 'self.amplitude_factor'
        ...
                nsg.set_amplitude(amplitude * self.amplitude_factor)

Now, the amplitude value is accessible on the thread, but we still need to customize the task runner to control it.
Try making the following class::

    class CustomTaskRunner(QMI_TaskRunner):
        @rpc_method
        def set_amplitude_factor(self, amplitude: float):
            if hasattr(self._thread.task, "amplitude_factor"):
                self._thread.task.amplitude_factor = amplitude

            else:
                raise qmi.core.exceptions.QMI_TaskRunException("No such attribute in task: 'amplitude_factor'")

And give it as the ``task_runner`` input when making the task, it is possible to change the value from outside the task.
We now also switch to use the internal context manager for tasks::

    ...
                with qmi.make_task("task", DemoTask, task_runner=CustomTaskRunner) as task:
                    print("the task has been started")
                    time.sleep(1)
                    task.set_amplitude_factor(1.0)
                    for i in range(5):
                        print("amplitude =", nsg.get_amplitude())
                        time.sleep(1)
                        # modify amplitude with factor

                   print("the task has been stopped")

With factor 1.0 we get our expected output:

>>> amplitude = 47.35139310000002
>>> amplitude = 24.663698713618015
>>> amplitude = 14.27385047108156
>>> amplitude = 12.340263428871816
>>> amplitude = 15.93705494741007

But by changing the factor to e.g. 0.9 we drift quickly to lower values:

>>> amplitude = 47.351393100000024
>>> amplitude = 27.404109681797806
>>> amplitude = 9.178708335524494
>>> amplitude = 8.384908374123494
>>> amplitude = 6.204404318848784

Or setting it to 1.1 we bounce back to large values:

>>> amplitude = 47.35139310000001
>>> amplitude = 30.14452064997758
>>> amplitude = 41.13632448440297
>>> amplitude = 56.13614532919599
>>> amplitude = 62.677189624461896

Let's build up the task and control in another way, making use of another custom task runner. In this example, we build the control
of the task in the script instead of inside the task. We now rewrite the script ``task_demo.py`` to be::

    #!/usr/bin/env python

    import time
    import qmi
    from qmi.utils.context_managers import start_stop
    from qmi.instruments.dummy.noisy_sine_generator import NoisySineGenerator
    from demo_task import DemoTask

    class CustomRpcControlTaskRunner(QMI_TaskRunner):
        @rpc_method
        def set_amplitude(self, amplitude: float):
            settings = self.get_settings()
            settings.amplitude = amplitude
            self.set_settings(settings)

    def main_2():
        with start_stop(qmi, "task_demo"):
            with qmi.make_instrument("nsg", NoisySineGenerator) as nsg:
                with qmi.make_task("task", DemoRpcControlTask, task_runner=CustomRpcControlTaskRunner) as task:
                    print("the task has been started")
                    for i in range(5):
                        sample = nsg.get_sample()
                        amplitude = nsg.get_amplitude()
                        print("sample =", sample, "amplitude =", amplitude)
                        if abs(sample) > 10:
                            task.set_amplitude(amplitude * 0.9)
                        else:
                            task.set_amplitude(amplitude * 1.1)
                        time.sleep(1)

                print("the task has been stopped")


    if __name__ == "__main__":
        main_2()

You can see now that the control of the amplitude is now done in this script instead of the task. For that we use the ``get_settings`` and ``set_settings``
methods of the **QMI_TaskRunner** class. We rewrite the file ``demo_task.py`` to make use of the ``self.settings`` attribute and ``update_settings`` method of **QMI_Task** class::

    from dataclasses import dataclass
    import qmi
    from qmi.core.task import QMI_Task
    from qmi.core.task import QMI_LoopTask


    @dataclass
    class DemoLoopTaskSettings:
        sample: float
        amplitude: float


    class DemoRpcControlTask(QMI_Task):

        def __init__(self, task_runner, name):
            super().__init__(task_runner, name)
            self.settings = DemoLoopTaskSettings(amplitude=100.0, sample=None)

        def run(self):
            print("starting the background task")
            nsg = qmi.get_instrument("task_demo.nsg")
            while not self.stop_requested():
                self.update_settings()
                nsg.set_amplitude(self.settings.amplitude)
                self.sleep(1.0)

Here, the initialization of the ``self.settings`` is done in the ``__init__`` of the task. The ``amplitude`` requires now
a valid value for start, ``sample`` can be initialized as ``None`` as it is calculated from ``amplitude`` in the instrument.
The task now checks the latest settings and uses the ``amplitude`` value of the settings to set new amplitude in the instrument.
The manipulation of the ``amplitude`` goes through the ``self.settings``, where the settings is manipulated by the custom task runner
class' ``CustomRpcControlTaskRunner.set_amplitude`` RPC method.

An example output is:

>>> sample = 8.592947545820666 amplitude = 100.0
>>> sample = 24.585371581587616 amplitude = 110.00000000000001
>>> sample = 28.763647335054355 amplitude = 99.00000000000001
>>> sample = 33.873943823248275 amplitude = 89.10000000000001
>>> sample = 39.12230323820781 amplitude = 80.19000000000001

Managing background processes
-----------------------------

A complex system often requires that several tasks are performed continuously.
It may be convenient to split these tasks up into separate Python programs.
This is not required; QMI makes it possible and easy to run multiple *tasks*
in a single Python program with the method demonstrated in the previous section.
However, running the tasks in separate programs can add flexibility and
also makes it possible to run some of the programs on separate computers.

After splitting up your project into many separate Python programs,
how do you start them all up in the morning and keep track of which
programs are running? That is where ``qmi_proc`` comes to the rescue.

``qmi_proc`` is a command-line tool to start and stop QMI processes
(by process, we simply mean a running program).
It can even manage programs on different computers via SSH.

``qmi_proc`` demo
=================

To demonstrate the use of ``qmi_proc``, let's create a QMI program
that keeps running, doing some thing, until explicitly told to stop.
A real background program would likely create instruments or tasks,
but our example program will just print messages.
For the program to be manageable by ``qmi_proc``, it must be implemented
as a Python module inside the module path of the project.
If you don't have a module path yet, just create a file ``proc_demo.py``
in the current directory::

    import time
    import qmi
    from qmi.utils.context_managers import start_stop

    def main():
        with start_stop(qmi, "proc_demo"):
            print("just started the background process")
            while not qmi.context().shutdown_requested():
                print("process is still running")
                time.sleep(1)
            print("process now stopping")

    if __name__ == "__main__":
        main()

Let's test that this program works when started manually
from the shell command-line::

    python -m proc_demo

Note the ``-m`` flag which tells the Python interpreter to load
this program as a module.
The program should start and keep printing messages.
Press ``Ctrl-C`` to stop it when you are ready to move on.

The next step is to change the QMI configuration file to set up
this program as a background process.
In the configuration data below, set the value of ``program_module``
to the fully qualified module path of the Python module that implements
the program (this is the same as the name following the ``-m`` flag above)::

  {
      # Log level for messages to the console.
      "logging": {
          "console_loglevel": "INFO"
      },

      "contexts": {
          # Testing remote instrument access.
          "instr_server": {
              "host": "127.0.0.1",
              "tcp_server_port": 40001
          },

          # Testing process management.
          "proc_demo": {
              "host": "127.0.0.1",
              "tcp_server_port": 40002,
              "enabled": true,
              "program_module": "proc_demo"
          }
      }
  }

Now we can manage the example program through ``qmi_proc``.
If your ``$PATH`` variable is set up correctly for QMI, you can
run the tool simply by typing ``qmi_proc`` at the shell command-line::

  qmi_proc status

Alternatively, you can run ``qmi_proc`` as a Python module::

  python -m qmi.tools.proc status

You should see a list of configured processes.
In this case the list contains just one process called ``proc_demo``
and should be reported as ``OFFLINE``.
Now let's start the background process by running::

  qmi_proc start proc_demo

This should set the process status to ``STARTED``.
The program will remain running in the background, with its output messages
redirected to a file ``proc_demo_<date>_<time>.out`` in the home directory.
Run ``qmi_proc status`` again to check that the program is still running.
After a while, run ``qmi_proc stop proc_demo`` to stop the background process.

Further options
===============

The ``qmi_proc`` provides also other options to facilitate starting and stopping processes. Beyond "start" and "stop" there are:
  - The "restart" option that simply calls first "stop" and then "start".
  - Together with "start", "stop" or "restart" you can also add arguments:

    * "--all" to (re)start/stop all configured contexts in the QMI configuration file.
    * "--locals" to (re)start/stop all configured LOCAL contexts.
    * "--config <path_to_config_file>" to specify the configuration file to be used.

Note that the "--all" and "--locals" options will work only for context in the configuration file that have
  - ``"enabled": true`` and
  - ``"program_module": "your.program.module"`` defined.

Also, you cannot start or stop processes that are not configured in the configuration file.
It is also possible to run the ``qmi_proc`` interactively in a "server" mode. Start it with::

  qmi_proc server <--config path/to/your.conf>

Then in the interactive mode type e.g.::

  START proc_demo

and then after it should be stopped::

  STOP proc_demo

At the moment no further commands are enabled and any other command exits the server.
This functionality might get deprecated in the future.

USBTMC devices
==============

Connecting with USBTMC devices on Windows can be tricky. Make sure you have libusb1 and pyvisa installed.
https://pypi.org/project/libusb1/ and https://pypi.org/project/PyVISA/ (and perhaps pyvisa-py).

Then you'll need to have the backend set-up correctly, in case the ``libusb-1.0.dll`` is not found in your path.
An example script to set-up and test the backend is
```python
import usb.core
from usb.backend import libusb1

backend = libusb1.get_backend(
    find_library=lambda x: "<path_to_your_env>\\Lib\\site-packages\\usb1\\libusb-1.0.dll")

dev = list(usb.core.find(find_all=True))
```

If you can now find devices, the backend is set correctly. There are of course other ways to set-up your backend
as well, but as said, it can be tricky...
