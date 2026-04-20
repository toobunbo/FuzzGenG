/**
 * @name Extract Python function signatures with type annotations
 * @description For fuzz driver generation: function name, file, parameter names and type hints
 * @kind table
 * @id py/tool-function-signatures
 */

import python

from Function f, Parameter p
where
  p = f.getAnArg() or p = f.getAKeywordOnlyArg() or p = f.getVararg() or p = f.getKwarg()
select
  f.getName() as name,
  f.getLocation().getFile().getRelativePath() as file,
  f.getLocation().getStartLine() as start_line,
  f.getLocation().getEndLine() as end_line,
  p.getName() as param_name,
  p.getAnnotation().toString() as param_type
