/**
 * @name Class __init__ signatures
 * @description Extract __init__ parameters for all classes
 * @kind table
 * @id py/extract/init-signatures
 */

import python

string getDefaultValue(Parameter p) {
    exists(p.getDefault()) and result = p.getDefault().toString()
    or
    not exists(p.getDefault()) and result = ""
}

from ClassDef c, Function init, Parameter p
where
    init = c.getDefinedClass().getAMethod() and
    init.getName() = "__init__" and
    p = init.getAnArg() and
    p.getName() != "self"
select
    c.getDefinedClass().getName()                    as class_name,
    c.getLocation().getFile().getRelativePath()      as class_file,
    c.getLocation().getStartLine()                   as class_line,
    p.getName()                                      as param_name,
    p.getPosition()                                  as param_index,
    p.getAnnotation().toString()                     as param_type,
    getDefaultValue(p)                               as default_value
order by class_file, class_name, param_index
