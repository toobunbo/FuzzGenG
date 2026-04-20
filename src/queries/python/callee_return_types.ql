/**
 * @name Callee return types
 * @description Extract return type annotations of called functions
 * @kind table
 * @id py/extract/callee-return-types
 */

import python

from Function caller, FunctionObject calleeObj, Expr ret
where
    calleeObj = caller.getFunctionObject().getACallee() and
    ret = calleeObj.getFunction().getDefinition().(FunctionExpr).getReturns()
select
    caller.getName()                                 as caller_name,
    caller.getLocation().getFile().getRelativePath() as caller_file,
    calleeObj.getName()                              as callee_name,
    calleeObj.getFunction().getLocation().getFile().getRelativePath()
                                                    as callee_file,
    ret.toString()                                   as return_type
order by caller_file, caller_name
