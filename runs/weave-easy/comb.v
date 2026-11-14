// Controller only: external tape supplies read_bit; move_right=0 means left.
module tm_comb(input read_bit,
          output reg [0:0] next_state,
          output reg write_bit, output reg move_right, output reg halt);
  wire [0:0] state = 1'b0; // A is the only state: zero register bits.
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
