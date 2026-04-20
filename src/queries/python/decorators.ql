/**
 * @name Function decorators
 * @description Extract decorators applied to Python functions
 * @kind table
 * @id py/extract/decorators
 */

import python

from Function f, Expr decorator
where decorator = f.getADecorator()
select
    f.getName()                                      as function_name,
    f.getLocation().getFile().getRelativePath()      as function_file,
    f.getLocation().getStartLine()                   as function_line,
    decorator.toString()                             as decorator_name
order by function_file, function_line
