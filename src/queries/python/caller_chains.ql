/**
 * @name Caller chains (depth 2)
 * @description Find functions called through 2 layers
 * @kind table
 * @id py/extract/caller-chains
 */

import python

from Function target, Function layer1, Function layer2
where
    layer1.getFunctionObject().getACallee().getFunction() = target and
    layer2.getFunctionObject().getACallee().getFunction() = layer1 and
    layer1 != target and
    layer2 != layer1 and
    not layer2.getName().matches("test_%")
select
    target.getName()                                 as target_name,
    target.getLocation().getFile().getRelativePath() as target_file,
    layer1.getName()                                 as layer1_caller,
    layer1.getLocation().getFile().getRelativePath() as layer1_file,
    layer2.getName()                                 as layer2_caller,
    layer2.getLocation().getFile().getRelativePath() as layer2_file
order by target_file, target_name
