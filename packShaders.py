import os
import subprocess
import re
import bisect

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
        self.spirv = None
        self.stage = stage

        with open(file, 'r') as glsl:
            self.glsl = glsl.read()

    def compile(self, find_snippet):
        file_parsed = self.name + ".parsed"
        file_output = self.file + ".spv"
        included = []

        def replace(match):
            snippet_name = match.group(1)

            if snippet_name in included:
                return ""

            included.append(snippet_name)

            return Shader.RE_INCLUDE.sub(replace, find_snippet(snippet_name))

        with open(file_parsed, 'w') as parsed:
            parsed.write(Shader.RE_INCLUDE.sub(replace, self.glsl))

        command = ["glslangValidator", "-V100", "-Os", file_parsed, "-S", self.stage, "-o", file_output]

        result = subprocess.run(command, stdout=subprocess.PIPE)

        if result.returncode != 0:
            print(f"Error compiling {file_parsed}:\n{result.stdout.decode()}")

            os.remove(file_parsed)
        else:
            with open(file_output, 'rb') as spirv:
                self.spirv = spirv.read()

        os.remove(file_parsed)
        os.remove(file_output)

        print(f"Compiled {self.name}: {len(self.spirv)}")

class Shaders:
    shaders = []
    snippets = []

    @staticmethod
    def pack_uint24(number):
        return number.to_bytes(3, byteorder="little")

    def __init__(self, directory):
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
            
    def compile(self, output_file):
        snippet_names = [snippet.name for snippet in self.snippets]
        
        def find_snippet(name):
            return self.snippets[bisect.bisect_left(snippet_names, name)].glsl

        with open(output_file, 'wb') as file:
            for shader in self.shaders:
                shader.compile(find_snippet)

                file.write(Shaders.pack_uint24(len(shader.spirv)))
                file.write(shader.name.encode("utf-8") + b'\0')
            
            file.write(Shaders.pack_uint24(0))

            for shader in self.shaders:
                file.write(shader.spirv)
        
        print(f"Wrote {output_file}")
        
Shaders("shaders/").compile("shaders.dat")