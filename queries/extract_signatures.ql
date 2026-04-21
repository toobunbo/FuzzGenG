/**
 * @name Extract Python function signatures with type annotations
 * @description Resolves actual Python type strings from annotations,
 *              handling Name, Union, Generic, Attribute, Callable, and unannotated params.
 * @kind table
 * @id py/tool-function-signatures
 */

import python

string resolveTuple(Tuple t) {
  if not exists(t.getElt(0)) then result = ""
  else if exists(t.getElt(0)) and not exists(t.getElt(1)) then result = resolveExpr(t.getElt(0))
  else if exists(t.getElt(1)) and not exists(t.getElt(2)) then result = resolveExpr(t.getElt(0)) + ", " + resolveExpr(t.getElt(1))
  else if exists(t.getElt(2)) and not exists(t.getElt(3)) then result = resolveExpr(t.getElt(0)) + ", " + resolveExpr(t.getElt(1)) + ", " + resolveExpr(t.getElt(2))
  else result = resolveExpr(t.getElt(0)) + ", " + resolveExpr(t.getElt(1)) + ", " + resolveExpr(t.getElt(2)) + ", ..."
}

string resolveList(List l) {
  if not exists(l.getElt(0)) then result = "[]"
  else if exists(l.getElt(0)) and not exists(l.getElt(1)) then result = "[" + resolveExpr(l.getElt(0)) + "]"
  else if exists(l.getElt(1)) and not exists(l.getElt(2)) then result = "[" + resolveExpr(l.getElt(0)) + ", " + resolveExpr(l.getElt(1)) + "]"
  else result = "[" + resolveExpr(l.getElt(0)) + ", " + resolveExpr(l.getElt(1)) + ", ...]"
}

string resolveExpr(Expr e) {
  if e instanceof Name
  then result = e.(Name).getId()
  else if e instanceof Attribute
  then result = resolveExpr(e.(Attribute).getObject()) + "." + e.(Attribute).getName()
  else if e instanceof BinaryExpr and e.(BinaryExpr).getOp() instanceof BitOr
  then result = resolveExpr(e.(BinaryExpr).getLeft()) + " | " + resolveExpr(e.(BinaryExpr).getRight())
  else if e instanceof Subscript
  then result = resolveExpr(e.(Subscript).getObject()) + "[" + resolveExpr(e.(Subscript).getIndex()) + "]"
  else if e instanceof Tuple
  then result = resolveTuple(e.(Tuple))
  else if e instanceof List
  then result = resolveList(e.(List))
  else result = e.toString()
}

from Function f, Parameter p
where
  f.getLocation().getFile().getRelativePath().matches("%.py") and
  (
    p = f.getAnArg() or
    p = f.getAKeywordOnlyArg() or
    p = f.getVararg() or
    p = f.getKwarg()
  )
select
  f.getName() as name,
  f.getLocation().getFile().getRelativePath() as file,
  f.getLocation().getStartLine() as start_line,
  f.getLocation().getEndLine() as end_line,
  p.getName() as param_name,
  resolveExpr(p.getAnnotation()) as param_type
