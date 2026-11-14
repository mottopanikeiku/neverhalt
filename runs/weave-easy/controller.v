// Controller only: external tape supplies read_bit; move_right=0 means left.
// clk advances one TM step; synchronous reset starts state A; halt freezes state.
module tm(input clk, input reset, input read_bit,
          output reg write_bit, output reg move_right, output reg halt);
  wire [0:0] state = 1'b0; // No state register needed.
  reg [0:0] next_state;
  always @* begin
    write_bit = read_bit; move_right = 1'b0; halt = 1'b1;
    next_state = state;
    case ({state, read_bit})
      2'd0: begin write_bit = 1'b1; move_right = 1'b1; halt = 1'b0; next_state = 1'd0; end
      2'd1: begin write_bit = 1'b1; move_right = 1'b1; halt = 1'b0; next_state = 1'd0; end
      default: begin end
    endcase
  end
endmodule
