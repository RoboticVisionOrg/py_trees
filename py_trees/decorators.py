#!/usr/bin/env python
#
# License: BSD
#   https://raw.githubusercontent.com/splintered-reality/py_trees/devel/LICENSE
#
##############################################################################
# Documentation
##############################################################################

"""
Decorators are behaviours that manage a single child and provide common
modifications to their underlying child behaviour (e.g. inverting the result).
That is, they provide a means for behaviours to wear different 'hats' and
this combinatorially expands the capabilities of your behaviour library.

.. image:: images/many-hats.png
   :width: 40px
   :align: center

An example:

.. graphviz:: dot/decorators.dot
.. literalinclude:: examples/decorators.py
   :language: python
   :linenos:


**Decorators (Hats)**

Decorators with very specific functionality:

* :class:`py_trees.decorators.Condition`
* :class:`py_trees.decorators.Inverter`
* :class:`py_trees.decorators.OneShot`
* :class:`py_trees.decorators.Timeout`

And the X is Y family:

* :class:`py_trees.decorators.FailureIsRunning`
* :class:`py_trees.decorators.FailureIsSuccess`
* :class:`py_trees.decorators.RunningIsFailure`
* :class:`py_trees.decorators.RunningIsSuccess`
* :class:`py_trees.decorators.SuccessIsFailure`
* :class:`py_trees.decorators.SuccessIsRunning`

**Decorators for Blocking Behaviours**

It is worth making a note of the effect of decorators on
behaviours that return :data:`~py_trees.common.Status.RUNNING` for
some time before finally returning  :data:`~py_trees.common.Status.SUCCESS`
or  :data:`~py_trees.common.Status.FAILURE` (blocking behaviours) since
the results are often at first, surprising.

A decorator, such as :class:`py_trees.decorators.RunningIsSuccess` on
a blocking behaviour will immediately terminate the underlying child and
re-intialise on it's next tick. This is necessary to ensure the underlying
child isn't left in a dangling state (i.e.
:data:`~py_trees.common.Status.RUNNING`), but is often not what is being
sought.

The typical use case being attempted is to convert the blocking
behaviour into a non-blocking behaviour. If the underlying child has no
state being modified in either the :meth:`~py_trees.behaviour.Behaviour.initialise`
or :meth:`~py_trees.behaviour.Behaviour.terminate` methods (e.g. machinery is
entirely launched at init or setup time), then conversion to a non-blocking
representative of the original succeeds. Otherwise, another approach is
needed. Usually this entails writing a non-blocking counterpart, or
combination of behaviours to affect the non-blocking characteristics.
"""

##############################################################################
# Imports
##############################################################################

import time

from . import behaviour
from . import common

##############################################################################
# Classes
##############################################################################

class Decorator(behaviour.Behaviour):
    """
    A decorator is responsible for handling the lifecycle of a single
    child beneath
    """
    def __init__(self, child, name=common.Name.AUTO_GENERATED):
        """
        Common initialisation steps for a decorator - type checks and
        name construction (if None is given).

        Args:
            name (:obj:`str`): the decorator name
            child (:class:`~py_trees.behaviour.Behaviour`): the child to be decorated

        Raises:
            TypeError: if the child is not an instance of :class:`~py_trees.behaviour.Behaviour`
        """
        # Checks
        if not isinstance(child, behaviour.Behaviour):
            raise TypeError("A decorator's child must be an instance of py_trees.behaviours.Behaviour")
        # Construct an informative name if none is provided 
        if not name or name == common.Name.AUTO_GENERATED:
            name = self.__class__.__name__ + "\n[{}]".format(child.name)
        # Initialise
        super(Decorator, self).__init__(name=name)
        self.children.append(child)
        # Give a convenient alias
        self.decorated = self.children[0]
        self.decorated.parent = self

    def setup(self, timeout):
        """
        Relays to the decorated child's :meth:`~py_trees.behaviour.Behaviour.setup`
        method.
        Args:
             timeout (:obj:`float`): time to wait (0.0 is blocking forever)
        Raises:
            TypeError: if children's setup methods fail to return a boolean
        Return:
            :obj:`bool`: suceess or failure of the operation
        """
        self.logger.debug("%s.setup()" % (self.__class__.__name__))
        result = self.decorated.setup(timeout)
        if type(result) != bool:
            message = "invalid return type from child's setup method (should be bool) [child:'{}'][type:'{}']".format(
                self.decorated.name, type(result))
            raise TypeError(message)
        return result
 
    def tick(self):
        """
        A decorator's tick is exactly the same as a normal proceedings for
        a Behaviour's tick except that it also ticks the decorated child node.

        Yields:
            :class:`~py_trees.behaviour.Behaviour`: a reference to itself or one of its children
        """
        self.logger.debug("%s.tick()" % self.__class__.__name__)
        # initialise just like other behaviours/composites
        if self.status != common.Status.RUNNING:
            self.initialise()
        # interrupt proceedings and process the child node
        # (including any children it may have as well)
        for node in self.decorated.tick():
            yield node
        # resume normal proceedings for a Behaviour's tick
        new_status = self.update()
        if new_status not in list(common.Status):
            self.logger.error("A behaviour returned an invalid status, setting to INVALID [%s][%s]" % (new_status, self.name))
            new_status = common.Status.INVALID
        if new_status != common.Status.RUNNING:
            self.stop(new_status)
        self.status = new_status
        yield self

    def stop(self, new_status):
        """
        As with other composites, it checks if the child is running
        and stops it if that is the case. 
        Args:
            new_status (:class:`~py_trees.common.Status`): the behaviour is transitioning to this new status
        """
        self.logger.debug("%s.stop(%s)" % (self.__class__.__name__, new_status))
        self.terminate(new_status)
        # priority interrupt handling
        if new_status == common.Status.INVALID:
            self.decorated.stop(new_status)
        # if the decorator returns SUCCESS/FAILURE and should stop the child
        if self.decorated.status == common.Status.RUNNING:
            self.decorated.stop(common.Status.INVALID)
        self.status = new_status

    def tip(self):
        """
        Get the *tip* of this behaviour's subtree (if it has one) after it's last
        tick. This corresponds to the the deepest node that was running before the
        subtree traversal reversed direction and headed back to this node.

        Returns:
            :class:`~py_trees.behaviour.Behaviour` or :obj:`None`: child behaviour, itself or :obj:`None` if its status is :data:`~py_trees.common.Status.INVALID`
        """
        if self.decorated.status != common.Status.INVALID:
            return self.decorated.tip()
        else:
            return super(Decorator, self).tip()


##############################################################################
# Decorators
##############################################################################

class Timeout(Decorator):
    """
    A decorator that applies a timeout pattern to an existing behaviour.
    If the timeout is reached, the encapsulated behaviour's
    :meth:`~py_trees.behaviour.Behaviour.stop` method is called with
    status :data:`~py_trees.common.Status.FAILURE` otherwise it will
    simply directly tick and return with the same status
    as that of it's encapsulated behaviour.
    """
    def __init__(self,
                 child,
                 name=common.Name.AUTO_GENERATED,
                 duration=5.0):
        """
        Init with the decorated child and a timeout duration.
        Args:
            child (:class:`~py_trees.behaviour.Behaviour`): behaviour to time
            name (:obj:`str`): the decorator name
            duration (:obj:`float`): timeout length in seconds
        """
        super(Timeout, self).__init__(name=name, child=child)
        self.duration = duration
        self.finish_time = None

    def initialise(self):
        """
        Reset the feedback message and finish time on behaviour entry.
        """
        self.finish_time = time.time() + self.duration
        self.feedback_message = ""
    def update(self):
        """
        Terminate the child and return :data:`~py_trees.common.Status.FAILURE`
        if the timeout is exceeded.
        """
        current_time = time.time()
        if current_time > self.finish_time:
            self.feedback_message = "timed out"
            self.logger.debug("{}.update() {}".format(self.__class__.__name__, self.feedback_message))
            # invalidate the decorated (i.e. cancel it), could also put this logic in a terminate() method
            self.decorated.stop(common.Status.INVALID)
            return common.Status.FAILURE
        # Don't show the time remaining, that will change the message every tick and make the tree hard to
        # debug since it will record a continuous stream of events
        self.feedback_message = self.decorated.feedback_message + " [timeout: {}]".format(self.finish_time)
        return self.decorated.status


class OneShot(Decorator):
    """
    A decorator that implements the oneshot pattern.
    This decorator ensures that the underlying child is ticked through
    to *successful* completion just once and while doing so, will return
    with the same status as it's child. Thereafter it will return
    :data:`~py_trees.common.Status.SUCCESS`.
    .. seealso:: :meth:`py_trees.idioms.oneshot`
    """
    def __init__(self, child,
                 name=common.Name.AUTO_GENERATED):
        """
        Init with the decorated child.
        Args:
            child (:class:`~py_trees.behaviour.Behaviour`): behaviour to time
            name (:obj:`str`): the decorator name
        """
        super(OneShot, self).__init__(name=name, child=child)
        self.final_status = None

    def update(self):
        """
        Bounce if the child has already successfully completed.
        """
        if self.final_status:
            self.logger.debug("{}.update()[bouncing]".format(self.__class__.__name__))
            return self.final_status
        return self.decorated.status
        
    def tick(self):
        """
        Select between decorator (single child) and behaviour (no children) style
        ticks depending on whether or not the underlying child has been ticked
        successfully to completion previously.
        """
        if self.final_status:
            # ignore the child
            for node in behaviour.Behaviour.tick(self):
                yield node
        else:
            # tick the child
            for node in Decorator.tick(self):
                yield node
                
    def terminate(self, new_status):
        """
        If returning :data:`~py_trees.common.Status.SUCCESS` for the first time,
        flag it so future ticks will block entry to the child.
        """
        if not self.final_status and new_status == common.Status.SUCCESS:
            self.logger.debug("{}.terminate({})[oneshot completed]".format(self.__class__.__name__, new_status))
            self.feedback_message = "oneshot completed"
            self.final_status = common.Status.SUCCESS
        else:
            self.logger.debug("{}.terminate({})".format(self.__class__.__name__, new_status))

class Inverter(Decorator):
    """
    A decorator that inverts the result of a class's update function.
    """
    def __init__(self, child, name=common.Name.AUTO_GENERATED):
        """
        Init with the decorated child.
                
        Args:
            child (:class:`~py_trees.behaviour.Behaviour`): behaviour to time
            name (:obj:`str`): the decorator name
        """
        super(Inverter, self).__init__(name=name, child=child)

    def update(self):
        """
        Flip :data:`~py_trees.common.Status.FAILURE` and
        :data:`~py_trees.common.Status.SUCCESS`

        Returns:
            :class:`~py_trees.common.Status`: the behaviour's new status :class:`~py_trees.common.Status`
        """
        if self.decorated.status == common.Status.SUCCESS:
            self.feedback_message = "success -> failure"
            return common.Status.FAILURE
        elif self.decorated.status == common.Status.FAILURE:
            self.feedback_message = "failure -> success"
            return common.Status.SUCCESS
        self.feedback_message = self.decorated.feedback_message
        return self.decorated.status


class RunningIsFailure(Decorator):
    """
    Got to be snappy! We want results...yesterday!
    """
    def update(self):
        """
        Return the decorated child's status unless it is
        :data:`~py_trees.common.Status.RUNNING` in which case, return
        :data:`~py_trees.common.Status.FAILURE`.
        Returns:
            :class:`~py_trees.common.Status`: the behaviour's new status :class:`~py_trees.common.Status`
        """
        if self.decorated.status == common.Status.RUNNING:
            self.feedback_message = "running is failure" + (" [%s]" % self.decorated.feedback_message if self.decorated.feedback_message else "")
            return common.Status.FAILURE
        else:
            self.feedback_message = self.decorated.feedback_message
            return self.decorated.status


class RunningIsSuccess(Decorator):
    """
    Don't hang around...
    """
    def update(self):
        """
        Return the decorated child's status unless it is
        :data:`~py_trees.common.Status.RUNNING` in which case, return
        :data:`~py_trees.common.Status.SUCCESS`.
        Returns:
            :class:`~py_trees.common.Status`: the behaviour's new status :class:`~py_trees.common.Status`
        """
        if self.decorated.status == common.Status.RUNNING:
            self.feedback_message = "running is success" + (" [%s]" % self.decorated.feedback_message if self.decorated.feedback_message else "")
            return common.Status.SUCCESS
        self.feedback_message = self.decorated.feedback_message
        return self.decorated.status


class FailureIsSuccess(Decorator):
    """
    Be positive, always succeed.
    """
    def update(self):
        """
        Return the decorated child's status unless it is
        :data:`~py_trees.common.Status.FAILURE` in which case, return
        :data:`~py_trees.common.Status.SUCCESS`.
        Returns:
            :class:`~py_trees.common.Status`: the behaviour's new status :class:`~py_trees.common.Status`
        """
        if self.decorated.status == common.Status.FAILURE:
            self.feedback_message = "failure is success" + (" [%s]" % self.decorated.feedback_message if self.decorated.feedback_message else "")
            return common.Status.SUCCESS
        self.feedback_message = self.decorated.feedback_message
        return self.decorated.status


class FailureIsRunning(Decorator):
    """
    Dont stop running.
    """
    def update(self):
        """
        Return the decorated child's status unless it is
        :data:`~py_trees.common.Status.FAILURE` in which case, return
        :data:`~py_trees.common.Status.RUNNING`.
        Returns:
            :class:`~py_trees.common.Status`: the behaviour's new status :class:`~py_trees.common.Status`
        """
        if self.decorated.status == common.Status.FAILURE:
            self.feedback_message = "failure is running" + (" [%s]" % self.decorated.feedback_message if self.decorated.feedback_message else "")
            return common.Status.RUNNING
        self.feedback_message = self.decorated.feedback_message
        return self.decorated.status


class SuccessIsFailure(Decorator):
    """
    Be depressed, always fail.
    """
    def update(self):
        """
        Return the decorated child's status unless it is
        :data:`~py_trees.common.Status.SUCCESS` in which case, return
        :data:`~py_trees.common.Status.FAILURE`.
        Returns:
            :class:`~py_trees.common.Status`: the behaviour's new status :class:`~py_trees.common.Status`
        """
        if self.decorated.status == common.Status.SUCCESS:
            self.feedback_message = "success is failure" + (" [%s]" % self.decorated.feedback_message if self.decorated.feedback_message else "")
            return common.Status.FAILURE
        self.feedback_message = self.decorated.feedback_message
        return self.decorated.status


class SuccessIsRunning(Decorator):
    """
    It never ends...
    """
    def update(self):
        """
        Return the decorated child's status unless it is
        :data:`~py_trees.common.Status.SUCCESS` in which case, return
        :data:`~py_trees.common.Status.RUNNING`.
        Returns:
            :class:`~py_trees.common.Status`: the behaviour's new status :class:`~py_trees.common.Status`
        """
        if self.decorated.status == common.Status.SUCCESS:
            self.feedback_message = "success is running [%s]" % self.decorated.feedback_message
            return common.Status.RUNNING
        self.feedback_message = self.decorated.feedback_message
        return self.decorated.status

class Condition(Decorator):
    """
    Encapsulates a behaviour and wait for it's status to flip to the
    desired state. This behaviour will tick with
    :data:`~py_trees.common.Status.RUNNING` while waiting and
    :data:`~py_trees.common.Status.SUCCESS` when the flip occurs.
    """
    def __init__(self,
                 child,
                 name=common.Name.AUTO_GENERATED,
                 status=common.Status.SUCCESS):
        """
        Initialise with child and optional name, status variables.

        Args:
            child (:class:`~py_trees.behaviour.Behaviour`): the child to be decorated
            name (:obj:`str`): the decorator name (can be None)
            status (:class:`~py_trees.common.Status`): the desired status to watch for
        """
        super(Condition, self).__init__(child, name)
        self.succeed_status = status

    def update(self):
        """
        :data:`~py_trees.common.Status.SUCCESS` if the decorated child has returned
        the specified status, otherwise :data:`~py_trees.common.Status.RUNNING`.
        This decorator will never return :data:`~py_trees.common.Status.FAILURE`
        Returns:
            :class:`~py_trees.common.Status`: the behaviour's new status :class:`~py_trees.common.Status`
        """
        self.logger.debug("%s.update()" % self.__class__.__name__)
        self.feedback_message = "'{0}' has status {1}, waiting for {2}".format(self.decorated.name, self.decorated.status, self.succeed_status)
        if self.decorated.status == self.succeed_status:
            return common.Status.SUCCESS
        return common.Status.RUNNING
