# Shader compiler
A utility for compiling GLSL to SPIRV and packing it into a single archive.

Recursive includes in the GLSL files are supported; `#include <file>` will inline `file.glsl`.

Only new or modified shaders are compiled, others are reused from the previous compilation.