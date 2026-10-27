// Resource lifetime is tested with the real service in file-lifecycle.cjs.
// Isolated rendering/network tests keep their existing filesystem mocks.
module.exports=context=>({
 registerTemporary:path=>path,
 registerOwnedResult:path=>path,
 retainFile:()=>()=>{},
 releaseTemporary:path=>context.uni?.getFileSystemManager?.()?.unlink?.({filePath:path,success:()=>{},fail:()=>{}}),
 withStorageRecovery:operation=>operation(),
})
