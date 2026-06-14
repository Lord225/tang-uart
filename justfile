set shell := ["zsh", "-cu"]

default:
    mkdir -p build
    yosys -p "read_verilog -sv rtl/top.sv; synth_gowin -top top -json build/top.json -family gw2a"
    nextpnr-himbaechel --json build/top.json --write build/top_pnr.json --device GW2AR-LV18QN88C8/I7 --vopt family=GW2A-18C --vopt cst=constraints/tangnano20k.cst
    gowin_pack -d GW2A-18C -o build/top.fs build/top_pnr.json

test:
    uv run pytest -q

dut-types:
    uv run python tools/generate_dut_types.py

visualize:
    python3 tools/visualize_pnr.py
    echo "Visualization written to build/top_visualization.html"

build-visualize: default visualize

schematic:
    mkdir -p build/schematic
    yosys -p "read_verilog -sv rtl/button.sv rtl/counter.sv rtl/top.sv; hierarchy -top top; proc; opt; show -format svg -prefix build/schematic/top -viewer none -stretch -width"

program: default
    openFPGALoader -b tangnano20k build/top.fs

flash: default
    openFPGALoader -b tangnano20k -f build/top.fs

clean:
    rm -rf build
