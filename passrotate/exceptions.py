import traceback

# Exceptions for control flow
class AbortFlowException(Exception):
    pass

class RetryFlowException(Exception):
    pass

class RestartStageException(Exception):
    pass

class PassRotateException(Exception):
    """For errors encountered during execution of a flow."""

    def explain(self):
        err = str(self)
        ctx = self.__context__
        if isinstance(ctx, PassRotateException):
            err += '\n' + ctx.explain()
        elif ctx is not None:
            return '\n'.join(traceback.format_exception(
                type(ctx), ctx, ctx.__traceback__))
        return err
