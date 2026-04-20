/**
 * @name Extract Python functions with scope
 * @description For fuzz driver generation: function name, file, line range, scope
 * @kind table
 * @id py/tool-functions
 */

import python

string getScopeStr(Function f) {
  if f.getScope() instanceof Class
  then result = f.getScope().(Class).getName()
  else result = ""
}

from Function f
select
  f.getName() as name,
  f.getLocation().getFile().getRelativePath() as file,
  f.getLocation().getStartLine() as start_line,
  f.getLocation().getEndLine() as end_line,
  getScopeStr(f) as scope
