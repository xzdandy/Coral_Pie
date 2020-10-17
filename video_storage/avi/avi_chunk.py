import chunk

file = open("ferst_atlantic.avi", "rb")

current_chunk = chunk.Chunk(file, bigendian=False)

print(current_chunk.getname())
print(current_chunk.getsize())

current_chunk.read(4)

current_chunk = chunk.Chunk(file, bigendian=False)

print(current_chunk.getname())
print(current_chunk.getsize())

current_chunk.read(4)

current_chunk = chunk.Chunk(file, bigendian=False)

print(current_chunk.getname())
print(current_chunk.getsize())

