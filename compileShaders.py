import os
import subprocess
import re
import bisect
import struct
import hashlib

class Cache:
    FILE_NAME = "shaderCache.dat"

    def __init__(self):
        self.entries = {}

    def store(self, name, hash):
        self.entries[name] = hash
    
    def load(self, name):
        if name not in self.entries:
            return None
        
        return self.entries[name]

    def read(self):
        if not os.path.exists(Cache.FILE_NAME):
            return
        
        with open(Cache.FILE_NAME, 'rb') as f:
            while True:
                key_bytes = bytearray()

                while (byte := f.read(1)) != b'\0':
                    if not byte:
                        return
                    
                    key_bytes.append(byte[0])

                self.entries[key_bytes.decode("utf-8")] = f.read(32).hex()

    def write(self):
        with open(Cache.FILE_NAME, 'wb') as file:
            for key in self.entries:
                file.write(key.encode("utf-8") + b'\0')
                file.write(bytes.fromhex(self.entries[key]))

class Snippet:
    def __init__(self, name, file):
        self.name = name

        with open(file, 'r') as glsl:
            self.glsl = glsl.read()

class Shader:
    RE_INCLUDE = re.compile(r"#include <(.*)>")

    def __init__(self, name, file, stage):
        self.name = name
        self.file = file
        self.glsl = None
        self.binary = None
        self.hash = None
        self.stage = stage

        with open(file, 'r') as glsl:
            self.glsl = glsl.read()

    def include_snippets(self, find_snippet):
        included = []

        def replace(match):
            snippet_name = match.group(1)

            if snippet_name in included:
                return ""

            included.append(snippet_name)

            return Shader.RE_INCLUDE.sub(replace, find_snippet(snippet_name))

        self.glsl = Shader.RE_INCLUDE.sub(replace, self.glsl)

        hasher = hashlib.new("sha256")
        hasher.update(self.glsl.encode())

        self.hash = hasher.hexdigest()

    def compile(self):
        file_parsed = self.name + ".parsed"
        file_output = self.file + ".spv"

        with open(file_parsed, 'w') as parsed:
            parsed.write(self.glsl)

        command = ["glslangValidator", "-V100", "-Os", file_parsed, "-S", self.stage, "-o", file_output]

        result = subprocess.run(command, stdout=subprocess.PIPE)

        if result.returncode != 0:
            print(f"Error compiling {file_parsed}:\n{result.stdout.decode()}")

            os.remove(file_parsed)
        else:
            with open(file_output, 'rb') as binary:
                self.binary = binary.read()

        os.remove(file_parsed)
        os.remove(file_output)

        print(f"Compiled {self.name}: {len(self.binary)}")
    
    def reuse(self, binary):
        self.binary = binary

class Shaders:
    FILE_NAME = "shaders.dat"

    shaders = []
    snippets = []
    previous = {}

    def __init__(self, directory):
        self.cache = Cache()
        self.cache.read()
        
        if os.path.exists(Shaders.FILE_NAME):
            with open(Shaders.FILE_NAME, "rb") as file:
                shaders = []

                while True:
                    length = int.from_bytes(file.read(4), "little")

                    if length == 0:
                        break

                    name_bytes = bytearray()

                    while (byte := file.read(1)) != b'\0':
                        name_bytes.append(byte[0])
                    
                    shaders.append((name_bytes.decode("utf-8"), length))

                for name, length in shaders:
                    self.previous[name] = file.read(length)

        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".glsl"):
                    file_name = os.path.splitext(file)[0]
                    file_path = os.path.join(root, file)

                    if file.endswith(".vert.glsl"):
                        self.shaders.append(Shader(file_name, file_path, "vert"))
                    elif file.endswith(".frag.glsl"):
                        self.shaders.append(Shader(file_name, file_path, "frag"))
                    elif file.endswith(".comp.glsl"):
                        self.shaders.append(Shader(file_name, file_path, "comp"))
                    else:
                        self.snippets.append(Snippet(file_name, file_path))
        
        self.shaders = sorted(self.shaders, key=lambda shader: shader.name)
        self.snippets = sorted(self.snippets, key=lambda snippet: snippet.name)

        snippet_names = [snippet.name for snippet in self.snippets]

        def find_snippet(name):
            return self.snippets[bisect.bisect_left(snippet_names, name)].glsl

        for shader in self.shaders:
            shader.include_snippets(find_snippet)
        
    def compile(self):
        cache_new = Cache()

        with open(Shaders.FILE_NAME, 'wb') as file:
            for shader in self.shaders:
                cache_new.store(shader.name, shader.hash)
                
                if shader.hash == self.cache.load(shader.name) and shader.name in self.previous:
                    print(f"Reused {shader.name}")

                    shader.reuse(self.previous[shader.name])
                else:
                    shader.compile()

                file.write(struct.pack('<I', len(shader.binary)))
                file.write(shader.name.encode("utf-8") + b'\0')
            
            file.write(struct.pack('<I', 0))

            for shader in self.shaders:
                file.write(shader.binary)
        
        cache_new.write()

        print(f"Wrote {Shaders.FILE_NAME}")
        
Shaders("shaders/").compile()